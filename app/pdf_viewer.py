"""
PDF Viewer widget (QGraphicsView-based).

- Viewer render ở DPI THẤP (mượt khi pan/zoom), ảnh trang được CACHE.
- Khi Extract, vùng chọn được render LẠI riêng ở DPI CAO (xem ocr_worker.py).

Vùng chọn (multi-region) — CROSS-PAGE:
  - Vùng chọn giờ được lưu theo trang (`self.selections: {page: [vùng...]}`)
    và KHÔNG bị xóa khi chuyển trang/zoom — chỉ bị xóa khi: xóa thủ công
    (Delete), mở file PDF khác, hoặc xoay trang (xem lý do trong
    rotate_page()).
  - Mỗi vùng có 1 "seq" nội bộ (thứ tự vẽ, không đổi, không hiển thị) dùng
    làm ID BẤT BIẾN để đồng bộ vị trí khi kéo-di-chuyển; và 1 "id" HIỂN THỊ
    được ĐÁNH SỐ LẠI (renumber) thành 1..N liên tục mỗi khi tập vùng chọn
    thay đổi (thêm/thay thế/xóa) — luôn đúng bằng tổng số vùng đang tồn tại,
    không bị nhảy số dù bạn vẽ-xóa-vẽ lại nhiều lần. Hiển thị trên canvas
    dạng nhãn "#<id>#<số trang>" (ví dụ "#1#12" = vùng số 1, ở trang 12).
  - get_all_selection_regions(): TẤT CẢ vùng chọn ở MỌI trang (dùng cho nút
    "Extract" thường — giờ OCR xuyên trang).
  - get_current_page_selection_rects(): CHỈ vùng chọn ở trang ĐANG XEM (dùng
    cho "Extract tất cả trang" — vùng ở trang khác không liên quan, không bị
    dùng làm mẫu).

Hotkeys (khi PDFViewer đang có focus — tự động lấy focus khi tương tác):
  - Enter        : yêu cầu Extract (phát signal extract_requested) — OCR tất
                    cả vùng đã đánh dấu, ở mọi trang.
  - Delete       : xóa TOÀN BỘ vùng chọn hiện có, ở MỌI trang.
  - Space        : bật "chế độ thêm vùng" — lần kéo chuột tiếp theo sẽ THÊM
                    một vùng chọn mới vào trang đang xem, KHÔNG xóa các vùng
                    đã có sẵn ở trang đó (và không đụng tới vùng ở trang
                    khác — vùng ở trang khác không bao giờ bị xóa chỉ vì bạn
                    vẽ vùng mới ở 1 trang khác).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Optional

import fitz
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .models import CONFIDENCE_RED_THRESHOLD, CONFIDENCE_YELLOW_THRESHOLD, RegionRef


class SelectionRectItem(QGraphicsRectItem):
    """Một vùng chọn OCR: có thể kéo để đổi vị trí (di chuyển).

    Sau khi OCR xong, màu viền/nền tự đổi theo độ tin cậy (confidence) —
    cảnh báo NHẸ (vàng)/NẶNG (đỏ) nếu dưới ngưỡng, giúp phát hiện nhanh vùng
    cần kiểm tra lại thủ công khi xử lý số lượng lớn. Chưa OCR (confidence
    = None) hoặc confidence cao: giữ màu xanh dương mặc định — không đổi gì
    so với trước.
    """

    _COLOR_DEFAULT = QColor(0, 140, 255)  # xanh dương — mặc định / chưa OCR / tin cậy cao
    _COLOR_WARNING = QColor(255, 179, 0)  # vàng — tin cậy trung bình
    _COLOR_DANGER = QColor(220, 53, 69)  # đỏ — tin cậy thấp, nên kiểm tra lại thủ công

    def __init__(self, rect: QRectF, region_seq: int, region_id: int, page_number: int,
                 confidence: Optional[float] = None):
        super().__init__(rect)
        self.region_seq = region_seq  # ID BẤT BIẾN (thứ tự vẽ) — dùng để đồng bộ khi kéo di chuyển
        self.region_id = region_id  # số hiển thị HIỆN TẠI (có thể đổi khi renumber)
        self.page_number = page_number
        self.confidence: Optional[float] = None
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(10)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        # Nhãn "#<id>#<trang>" (kèm "(NN%)" nếu đã có confidence) — vd
        # "#1#12 (54%)" = vùng số 1, ở trang 12, độ tin cậy 54%.
        self._label = QGraphicsSimpleTextItem("", self)
        self._label.setFont(QFont("Sans Serif", 10, QFont.Weight.Bold))
        self._label.setPos(rect.left() + 2, rect.top() - 16)
        self._label.setZValue(11)

        self.set_confidence(confidence)  # áp màu + nhãn ban đầu (kể cả khi None -> mặc định)

    def set_display(self, region_id: int, page_number: int):
        """Cập nhật số hiển thị (sau khi renumber) mà không cần tạo lại item."""
        self.region_id = region_id
        self.page_number = page_number
        self._refresh_label()

    def set_confidence(self, confidence: Optional[float]):
        """Cập nhật độ tin cậy sau khi OCR xong — đổi màu cảnh báo tương ứng."""
        self.confidence = confidence
        if confidence is None or confidence >= CONFIDENCE_YELLOW_THRESHOLD:
            color = self._COLOR_DEFAULT
        elif confidence >= CONFIDENCE_RED_THRESHOLD:
            color = self._COLOR_WARNING
        else:
            color = self._COLOR_DANGER
        self.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 40)))
        self._refresh_label()

    def _refresh_label(self):
        text = f"#{self.region_id}#{self.page_number + 1}"
        if self.confidence is not None:
            text += f" ({round(self.confidence)}%)"
        self._label.setText(text)
        self._label.setBrush(QBrush(self.pen().color()))


class PDFViewer(QGraphicsView):
    page_changed = Signal(int, int)  # current (1-based), total
    selection_changed = Signal(bool)  # có vùng chọn nào không (ở BẤT KỲ trang nào)
    extract_requested = Signal()  # người dùng bấm Enter để yêu cầu Extract

    LOW_DPI = 120
    HIGH_DPI = 300
    # Giới hạn số trang (đã render, theo từng góc xoay) giữ trong bộ nhớ cùng
    # lúc — tránh RAM phình to không kiểm soát với PDF hàng trăm/nghìn trang
    # nếu người dùng lướt qua nhiều trang. LRU: trang lâu không xem tới bị
    # loại trước; trang đang xem luôn được giữ lại.
    MAX_CACHED_PAGES = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(60, 60, 60)))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.doc: Optional[fitz.Document] = None
        self.doc_path: Optional[str] = None
        self.current_page = 0
        self.rotation = 0
        self.zoom_factor = 1.0

        self.pixmap_item: Optional[QGraphicsPixmapItem] = None

        # Nguồn dữ liệu THẬT SỰ của vùng chọn — độc lập với vòng đời của
        # QGraphicsItem (vốn bị hủy mỗi khi đổi trang do self._scene.clear()).
        # {số trang (0-based): [{"seq": int (bất biến), "id": int (hiển thị,
        # được renumber liên tục), "rect": QRectF (scene coords, đã gộp cả
        # offset kéo-di-chuyển nếu có)}, ...]}
        self.selections: Dict[int, List[dict]] = {}
        self._next_seq = 1  # tăng dần, KHÔNG reset khi đổi trang — chỉ dùng nội bộ, KHÔNG hiển thị

        # Các SelectionRectItem đang hiển thị THẬT trên scene — chỉ tương
        # ứng với self.selections[self.current_page] (item của trang khác
        # không tồn tại dưới dạng QGraphicsItem cho tới khi quay lại trang đó).
        self._displayed_items: List[SelectionRectItem] = []

        self._add_mode = False  # True sau khi bấm Space: lần vẽ tiếp theo sẽ THÊM vùng, không thay thế
        self._page_cache: "OrderedDict[tuple[int, int], QPixmap]" = OrderedDict()

        self._drawing = False
        self._draw_start = QPointF()
        self._temp_rect_item: Optional[QGraphicsRectItem] = None

    # ---------------- Loading ----------------
    def load_pdf(self, path: str) -> bool:
        try:
            doc = fitz.open(path)
            if doc.page_count == 0:
                doc.close()
                return False
        except Exception:
            return False

        if self.doc:
            self.doc.close()

        self.doc = doc
        self.doc_path = path
        self.current_page = 0
        self.rotation = 0
        self.zoom_factor = 1.0
        self._page_cache.clear()
        self.selections = {}
        # KHÔNG reset self._next_seq ở đây: nếu vẫn còn 1 worker OCR nền của
        # tài liệu TRƯỚC đó chưa kịp trả kết quả, việc reset có thể khiến
        # seq bị cấp lại trùng với vùng chọn MỚI trên tài liệu này, làm
        # confidence trả về muộn bị áp nhầm sang vùng khác. seq chỉ cần tăng
        # dần mãi mãi trong vòng đời widget, không cần bắt đầu lại từ 1.
        self._displayed_items = []
        self._render_current_page()
        self.page_changed.emit(self.current_page + 1, len(self.doc))
        self.setFocus()
        return True

    @property
    def page_count(self) -> int:
        return len(self.doc) if self.doc else 0

    # ---------------- Rendering ----------------
    def _render_current_page(self):
        if not self.doc:
            return

        key = (self.current_page, self.rotation)
        pixmap = self._page_cache.get(key)
        if pixmap is not None:
            self._page_cache.move_to_end(key)  # vừa dùng -> đánh dấu "mới nhất" cho LRU
        else:
            page = self.doc[self.current_page]
            mat = fitz.Matrix(self.LOW_DPI / 72, self.LOW_DPI / 72).prerotate(self.rotation)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            fmt = QImage.Format.Format_RGB888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            pixmap = QPixmap.fromImage(qimg.copy())  # copy() vì buffer của pix sẽ bị giải phóng
            self._page_cache[key] = pixmap
            if len(self._page_cache) > self.MAX_CACHED_PAGES:
                self._page_cache.popitem(last=False)  # loại bỏ trang lâu không dùng nhất

        self._scene.clear()  # hủy pixmap cũ + mọi SelectionRectItem đang hiển thị (sẽ dựng lại bên dưới)
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.pixmap_item.setZValue(0)
        self._scene.addItem(self.pixmap_item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

        # Dựng lại (từ self.selections — nguồn dữ liệu thật) các vùng chọn
        # thuộc ĐÚNG trang đang xem — vùng ở trang khác vẫn còn nguyên trong
        # self.selections, chỉ là chưa có QGraphicsItem hiển thị cho tới khi
        # người dùng quay lại trang đó. "id" đã đúng sẵn (do renumber chạy
        # ngay khi có thay đổi), không cần renumber lại ở đây.
        self._displayed_items = []
        for entry in self.selections.get(self.current_page, []):
            item = SelectionRectItem(
                entry["rect"], entry["seq"], entry["id"], self.current_page,
                confidence=entry.get("confidence"),
            )
            self._scene.addItem(item)
            self._displayed_items.append(item)

        self._add_mode = False
        self.selection_changed.emit(self.has_selection())

        self.resetTransform()
        self.scale(self.zoom_factor, self.zoom_factor)

    def _sync_current_page_positions(self):
        """Đồng bộ lại self.selections[current_page] theo vị trí THẬT SỰ hiện
        tại của các SelectionRectItem đang hiển thị (phòng trường hợp người
        dùng vừa kéo di chuyển 1 vùng) — gọi TRƯỚC khi đổi trang hoặc trước
        khi đọc dữ liệu vùng chọn ra để OCR/xuất tọa độ."""
        if not self._displayed_items:
            return
        entries_by_seq = {e["seq"]: e for e in self.selections.get(self.current_page, [])}
        for item in self._displayed_items:
            entry = entries_by_seq.get(item.region_seq)
            if entry is not None:
                entry["rect"] = item.rect().translated(item.pos())

    def goto_page(self, index: int):
        if not self.doc:
            return
        index = max(0, min(index, len(self.doc) - 1))
        if index == self.current_page:
            return
        self._sync_current_page_positions()
        self.current_page = index
        self._render_current_page()
        self.page_changed.emit(self.current_page + 1, len(self.doc))

    def next_page(self):
        self.goto_page(self.current_page + 1)

    def prev_page(self):
        self.goto_page(self.current_page - 1)

    def rotate_page(self, delta_degrees: int = 90):
        # Rotation áp dụng cho TOÀN BỘ tài liệu (không phải riêng 1 trang).
        # Vùng chọn được lưu theo tọa độ pixel (LOW_DPI) dưới góc xoay HIỆN
        # TẠI — nếu đổi góc xoay mà vẫn giữ lại các vùng cũ thì vị trí OCR sẽ
        # sai lệch trên mọi trang. Vì vậy: xoay trang sẽ xóa TOÀN BỘ vùng
        # chọn đang có (ở mọi trang) — main_window.py sẽ hỏi xác nhận trước
        # nếu đang có vùng chọn, tránh mất dữ liệu ngoài ý muốn.
        if not self.doc:
            return
        if self.selections:
            for item in self._displayed_items:
                self._scene.removeItem(item)
            self.selections = {}
            self._next_seq = 1
            self._displayed_items = []
        self.rotation = (self.rotation + delta_degrees) % 360
        self._render_current_page()

    # ---------------- Zoom ----------------
    def zoom_in(self):
        self.set_zoom_percent(self.zoom_percent() * 1.2)

    def zoom_out(self):
        self.set_zoom_percent(self.zoom_percent() / 1.2)

    def zoom_percent(self) -> int:
        return round(self.zoom_factor * 100)

    def set_zoom_percent(self, percent: float):
        """Đặt trực tiếp mức zoom theo % (dùng cho ô nhập tỉ lệ zoom)."""
        percent = max(20, min(percent, 600))
        new_factor = percent / 100
        if self.pixmap_item is not None:
            ratio = new_factor / self.zoom_factor if self.zoom_factor else 1.0
            self.scale(ratio, ratio)
        self.zoom_factor = new_factor

    # ---------------- Selection (multi-region, cross-page) ----------------
    def has_selection(self) -> bool:
        """Có vùng chọn nào không, ở BẤT KỲ trang nào."""
        return any(self.selections.values())

    def has_current_page_selection(self) -> bool:
        """Có vùng chọn nào ở trang ĐANG XEM không — dùng cho 'Extract tất cả trang'."""
        return bool(self.selections.get(self.current_page))

    @property
    def selection_count(self) -> int:
        """Tổng số vùng chọn, tính trên MỌI trang."""
        return sum(len(v) for v in self.selections.values())

    def _renumber(self):
        """Đánh số lại "id" hiển thị của TẤT CẢ vùng chọn (mọi trang) thành
        1..N liên tục, theo đúng thứ tự đã vẽ (seq tăng dần) — luôn khớp với
        tổng số vùng đang tồn tại, không bị nhảy số dù đã vẽ/xóa/thay thế
        nhiều lần. Gọi sau MỌI thay đổi tới self.selections."""
        all_entries = [e for entries in self.selections.values() for e in entries]
        all_entries.sort(key=lambda e: e["seq"])
        for new_id, entry in enumerate(all_entries, start=1):
            entry["id"] = new_id
        self._refresh_displayed_labels()

    def _refresh_displayed_labels(self):
        """Cập nhật lại nhãn của các SelectionRectItem đang hiển thị (trang
        hiện tại) theo "id" mới nhất trong self.selections."""
        entries_by_seq = {e["seq"]: e for e in self.selections.get(self.current_page, [])}
        for item in self._displayed_items:
            entry = entries_by_seq.get(item.region_seq)
            if entry is not None and entry["id"] != item.region_id:
                item.set_display(entry["id"], self.current_page)

    def clear_selection(self):
        """Xóa TOÀN BỘ vùng chọn hiện có, ở MỌI trang (phím Delete)."""
        for item in self._displayed_items:
            self._scene.removeItem(item)
        self._displayed_items = []
        self.selections = {}
        # KHÔNG reset self._next_seq — xem ghi chú trong load_pdf().
        self.selection_changed.emit(False)

    def _replace_current_page_selection(self):
        """Xóa CHỈ vùng chọn ở trang đang xem (không đụng tới vùng ở trang
        khác) — dùng khi bắt đầu vẽ vùng mới mà KHÔNG ở 'chế độ thêm'."""
        for item in self._displayed_items:
            self._scene.removeItem(item)
        self._displayed_items = []
        if self.selections.pop(self.current_page, None) is not None:
            self._renumber()  # đóng khoảng trống số ngay, kể cả nếu chưa vẽ vùng mới

    def _qrect_to_page_rect(self, rect: QRectF) -> "fitz.Rect":
        mat = fitz.Matrix(self.LOW_DPI / 72, self.LOW_DPI / 72).prerotate(self.rotation)
        inv = ~mat
        p0 = fitz.Point(rect.left(), rect.top()) * inv
        p1 = fitz.Point(rect.right(), rect.bottom()) * inv
        return fitz.Rect(p0, p1).normalize()

    def get_all_selection_regions(self) -> List[RegionRef]:
        """TẤT CẢ vùng chọn ở MỌI trang, theo đúng thứ tự đã vẽ (id tăng
        dần liên tục, 1..N) — dùng cho nút Extract thường (giờ OCR xuyên
        trang)."""
        if not self.doc:
            return []
        self._sync_current_page_positions()
        refs = []
        for page_no, entries in self.selections.items():
            for entry in entries:
                refs.append(RegionRef(entry["id"], entry["seq"], page_no, self._qrect_to_page_rect(entry["rect"])))
        refs.sort(key=lambda r: r.id)
        return refs

    def get_current_page_selection_rects(self) -> List["fitz.Rect"]:
        """CHỈ vùng chọn ở trang ĐANG XEM (bỏ qua vùng ở trang khác) — dùng
        làm MẪU cho 'Extract tất cả trang'."""
        if not self.doc:
            return []
        self._sync_current_page_positions()
        entries = sorted(self.selections.get(self.current_page, []), key=lambda e: e["id"])
        return [self._qrect_to_page_rect(e["rect"]) for e in entries]

    def set_region_confidence(self, region_seq: int, confidence: Optional[float]):
        """Gán độ tin cậy (sau khi OCR xong) cho vùng chọn có `seq` tương
        ứng — dùng `seq` (bất biến) chứ KHÔNG dùng `id` hiển thị, vì `id` có
        thể đã bị renumber trong lúc worker OCR chạy nền (người dùng vẫn có
        thể vẽ/xóa vùng khác trong lúc đó do UI không bị chặn) — nếu dùng
        `id` sẽ có rủi ro tô nhầm màu cảnh báo sang vùng khác. Nếu vùng đó
        đã bị xóa trước khi kết quả trả về thì bỏ qua im lặng (không lỗi)."""
        for page_no, entries in self.selections.items():
            for entry in entries:
                if entry["seq"] == region_seq:
                    entry["confidence"] = confidence
                    if page_no == self.current_page:
                        for item in self._displayed_items:
                            if item.region_seq == region_seq:
                                item.set_confidence(confidence)
                    return

    def apply_region_confidences(self, confidences_by_seq: Dict[int, Optional[float]]):
        """Áp dụng hàng loạt kết quả confidence (key = seq) sau khi 1 lượt
        Extract hoàn tất — xem set_region_confidence()."""
        for region_seq, confidence in confidences_by_seq.items():
            self.set_region_confidence(region_seq, confidence)

    # ---------------- Mouse events: vẽ / di chuyển vùng chọn ----------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.pixmap_item is not None:
            scene_pos = self.mapToScene(event.pos())
            item = self._scene.itemAt(scene_pos, self.transform())
            if isinstance(item, SelectionRectItem):
                # Cho phép item tự xử lý việc di chuyển (ItemIsMovable)
                super().mousePressEvent(event)
                self.setFocus()
                return

            # Bắt đầu vẽ vùng chọn mới trên trang đang xem.
            # Mặc định: thay thế các vùng cũ CỦA TRANG NÀY (không đụng tới
            # vùng ở trang khác). Nếu đang ở "chế độ thêm" (vừa bấm Space):
            # giữ nguyên vùng cũ của trang này, chỉ thêm vùng mới.
            if not self._add_mode:
                self._replace_current_page_selection()
            self._drawing = True
            self._draw_start = scene_pos
            pen = QPen(QColor(0, 140, 255), 2, Qt.PenStyle.DashLine)
            self._temp_rect_item = self._scene.addRect(QRectF(scene_pos, scene_pos), pen)
            self._temp_rect_item.setZValue(10)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing and self._temp_rect_item is not None:
            scene_pos = self.mapToScene(event.pos())
            rect = QRectF(self._draw_start, scene_pos).normalized()
            self._temp_rect_item.setRect(rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drawing and self._temp_rect_item is not None:
            rect = self._temp_rect_item.rect()
            self._scene.removeItem(self._temp_rect_item)
            self._temp_rect_item = None
            self._drawing = False
            self._add_mode = False  # "chế độ thêm" chỉ áp dụng cho đúng 1 lần vẽ kế tiếp

            if rect.width() > 5 and rect.height() > 5:
                # Giới hạn trong biên trang
                page_bounds = self._scene.sceneRect()
                rect = rect.intersected(page_bounds)

                seq = self._next_seq
                self._next_seq += 1
                entry = {"seq": seq, "id": 0, "rect": rect, "confidence": None}  # "id" thật sẽ được _renumber() điền ngay dưới đây
                self.selections.setdefault(self.current_page, []).append(entry)
                self._renumber()  # đánh số lại 1..N cho TẤT CẢ vùng (kể cả vùng đang hiển thị ở trang khác, nếu có)

                new_item = SelectionRectItem(rect, seq, entry["id"], self.current_page)
                self._scene.addItem(new_item)
                self._displayed_items.append(new_item)
                self.selection_changed.emit(True)
            else:
                self.selection_changed.emit(self.has_selection())
            self.setFocus()
            return
        super().mouseReleaseEvent(event)

    # ---------------- Keyboard events ----------------
    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.has_selection():
                self.extract_requested.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Delete:
            self.clear_selection()
            event.accept()
            return
        if key == Qt.Key.Key_Space:
            self._add_mode = True
            event.accept()
            return
        super().keyPressEvent(event)
