"""
Worker chạy OCR trong background thread (QThread) — không chặn UI.

Flow (đúng theo core flow đã thiết kế):
  render lại vùng chọn ở DPI CAO (clip) -> preprocess -> OCR -> postprocess -> emit signal.

table_mode:
  - None          : OCR text thường (mặc định).
  - "heuristic"   : Table detection nhẹ — dựng bảng markdown từ box từ/dòng
                    (engine-agnostic, dùng engine.recognize_words()).
  - "pp_structure": Table detection nâng cao qua PP-Structure — CHỈ hỗ trợ khi
                    engine là PaddleOCR (engine.recognize_table()); nếu engine
                    không hỗ trợ, lỗi sẽ được raise (finished qua signal failed).

parallel (chỉ MultiRegionOCRWorker/BatchOCRWorker, mặc định TẮT):
  - Chạy song song nhiều vùng/trang cùng lúc bằng ThreadPoolExecutor — CHỈ
    áp dụng khi engine là Tesseract (mỗi lần gọi là 1 tiến trình con độc
    lập, an toàn để chạy đồng thời). PaddleOCR LUÔN chạy tuần tự (1 model
    instance dùng chung, gọi đồng thời từ nhiều thread không an toàn).
  - Thứ tự kết quả trong text trả về LUÔN giống hệt chế độ tuần tự (được
    sắp xếp lại theo đúng thứ tự vùng/trang gốc sau khi tất cả hoàn tất,
    không phụ thuộc thứ tự hoàn thành thực tế) — bật/tắt song song KHÔNG
    làm thay đổi định dạng/nội dung kết quả, chỉ đổi tốc độ.
"""
from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import fitz
import numpy as np
from PySide6.QtCore import QThread, Signal

from .models import CONFIDENCE_RED_THRESHOLD, CONFIDENCE_YELLOW_THRESHOLD, RegionRef
from .preprocessing import preprocess_image
from .table_detect import words_to_markdown_table
from .text_postprocess import postprocess_text


def _render_clip_as_array(page: "fitz.Page", clip_rect: "fitz.Rect", dpi_high: int, rotation: int) -> np.ndarray:
    mat = fitz.Matrix(dpi_high / 72, dpi_high / 72).prerotate(rotation)
    pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
    if pix.width == 0 or pix.height == 0:
        raise ValueError("Vùng chọn không hợp lệ (kích thước bằng 0) sau khi render.")
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return img


def _confidence_warning_prefix(conf: Optional[float]) -> str:
    """Dòng cảnh báo chèn vào ĐẦU text khi confidence dưới ngưỡng — hỗ trợ
    khâu kiểm soát chất lượng khi xử lý số lượng lớn (có thể grep/tìm nhanh
    ký tự cảnh báo trong output thay vì đọc từng vùng/trang). Rỗng nếu
    confidence None (engine không hỗ trợ) hoặc đủ cao — không đổi gì so với
    hành vi cũ trong các trường hợp đó."""
    if conf is None:
        return ""
    if conf < CONFIDENCE_RED_THRESHOLD:
        return f"⚠️ [ĐỘ TIN CẬY THẤP — {round(conf)}%, nên kiểm tra lại thủ công]\n"
    if conf < CONFIDENCE_YELLOW_THRESHOLD:
        return f"⚠ [Độ tin cậy trung bình — {round(conf)}%]\n"
    return ""


def _run_ocr_on_clip(
    page: "fitz.Page",
    clip_rect,
    dpi_high: int,
    rotation: int,
    engine,
    lang: str,
    table_mode: Optional[str] = None,
) -> Tuple[str, Optional[float]]:
    img = _render_clip_as_array(page, clip_rect, dpi_high, rotation)
    # Engine deep-learning (PaddleOCR) hoạt động tốt hơn trên ảnh xám (không ép nhị phân cứng)
    binarize = getattr(engine, "name", "") == "tesseract"
    processed = preprocess_image(img, binarize=binarize)

    if table_mode == "pp_structure":
        text = engine.recognize_table(processed, lang)
        if text is None:
            raise RuntimeError(
                "Engine hiện tại không hỗ trợ Table detection (PP-Structure). "
                "Hãy đổi Engine sang PaddleOCR hoặc chọn chế độ Table 'Heuristic'."
            )
        return text, None  # PP-Structure không có confidence tổng hợp sẵn -> không cảnh báo được

    if table_mode == "heuristic":
        words = engine.recognize_words(processed, lang)
        text = words_to_markdown_table(words)
        confs = [w["conf"] for w in words if w.get("conf") is not None]
        confidence = (sum(confs) / len(confs)) if confs else None
        return _confidence_warning_prefix(confidence) + text, confidence

    text, confidence = engine.recognize(processed, lang)
    text = postprocess_text(text)
    return _confidence_warning_prefix(confidence) + text, confidence


def _run_ocr_standalone(
    doc_path: str,
    page_no: int,
    clip_rect,
    dpi_high: int,
    rotation: int,
    engine,
    lang: str,
    table_mode: Optional[str],
) -> Tuple[str, Optional[float]]:
    """Bản độc lập của _run_ocr_on_clip — TỰ MỞ RIÊNG 1 fitz.Document cho
    tác vụ này rồi đóng lại ngay sau khi xong. Dùng CHO CHẾ ĐỘ SONG SONG:
    PyMuPDF/MuPDF không đảm bảo an toàn khi nhiều thread cùng dùng chung 1
    fitz.Document — mỗi thread cần Document riêng của mình. Chi phí mở file
    thêm vài lần không đáng kể so với thời gian OCR."""
    doc = fitz.open(doc_path)
    try:
        page = doc[page_no]
        return _run_ocr_on_clip(page, clip_rect, dpi_high, rotation, engine, lang, table_mode)
    finally:
        doc.close()


def _fmt_conf(conf: Optional[float]) -> Optional[str]:
    if conf is None:
        return None
    return f"{round(conf)}%"


def _max_parallel_workers(n_tasks: int) -> int:
    return max(1, min(n_tasks, os.cpu_count() or 4))


class EngineInitWorker(QThread):
    """Khởi tạo OCR engine trong background thread — tránh đơ UI. PaddleOCR
    có thể mất vài giây tới vài chục giây (lần đầu còn phải tải model), nếu
    làm trên main thread thì toàn bộ UI (kể cả progress bar) sẽ đơ cứng
    trong lúc đó vì event loop bị chặn."""

    finished_ok = Signal(object)  # BaseOCREngine instance
    failed = Signal(str)

    def __init__(self, engine_name: str, parent=None):
        super().__init__(parent)
        self.engine_name = engine_name

    def run(self):
        try:
            from .ocr_engine import create_engine

            engine = create_engine(self.engine_name)
            self.finished_ok.emit(engine)
        except Exception as e:
            self.failed.emit(str(e))


class MultiRegionOCRWorker(QThread):
    """OCR cho TẤT CẢ vùng chọn đã đánh dấu — có thể nằm ở NHIỀU TRANG khác
    nhau (cross-page multi-region). Mỗi vùng luôn OCR đúng trên trang riêng
    của nó (region.page).

    Kết quả các vùng nối bằng '---' (không chèn thêm nhãn số/trang vào text
    — muốn biết vùng nào ở trang nào, xem nhãn "#<id>#<trang>" trên canvas
    lúc đang chọn vùng).

    finished_ok(text, confidence_summary, confidences_by_seq):
      - confidence_summary: chuỗi hiển thị sẵn cho status bar — rỗng nếu
        engine không trả về confidence nào.
      - confidences_by_seq: dict {region.seq: confidence} — dùng để tô màu
        cảnh báo lại trên canvas (PDFViewer.apply_region_confidences). Dùng
        `seq` (bất biến) chứ không dùng `id` hiển thị (có thể đã đổi nếu
        người dùng chỉnh sửa vùng chọn trong lúc worker này đang chạy).
    """

    progress = Signal(str)
    finished_ok = Signal(str, str, dict)
    failed = Signal(str)

    def __init__(self, doc_path, regions: List[RegionRef], dpi_high, lang, engine, rotation=0,
                 table_mode: Optional[str] = None, parallel: bool = False, parent=None):
        super().__init__(parent)
        self.doc_path = doc_path
        self.regions = list(regions)  # đã sắp theo đúng thứ tự vẽ (id tăng dần) — xem PDFViewer.get_all_selection_regions()
        self.dpi_high = dpi_high
        self.lang = lang
        self.engine = engine
        self.rotation = rotation
        self.table_mode = table_mode
        # Song song chỉ thực sự bật khi: được yêu cầu, engine là Tesseract,
        # và có từ 2 vùng trở lên (1 vùng thì chạy song song không có ý nghĩa).
        self.parallel = bool(parallel) and getattr(engine, "name", "") == "tesseract" and len(self.regions) > 1

    def run(self):
        try:
            results = self._run_parallel() if self.parallel else self._run_sequential()

            multi = len(results) > 1
            combined_text = "\n---\n".join(text for _region, text, _conf in results)
            confidence_summary = self._build_confidence_summary(results, multi)
            confidences_by_seq = {region.seq: conf for region, _text, conf in results}
            self.finished_ok.emit(combined_text, confidence_summary, confidences_by_seq)
        except Exception as e:
            self.failed.emit(str(e))

    def _run_sequential(self) -> List[Tuple[RegionRef, str, Optional[float]]]:
        doc = fitz.open(self.doc_path)
        results: List[Tuple[RegionRef, str, Optional[float]]] = []
        total = len(self.regions)
        try:
            for i, region in enumerate(self.regions, start=1):
                self.progress.emit(
                    f"Đang OCR vùng #{region.id} (Trang {region.page + 1}) — {i}/{total}..."
                )
                page = doc[region.page]
                text, conf = _run_ocr_on_clip(
                    page, region.rect, self.dpi_high, self.rotation, self.engine, self.lang, self.table_mode
                )
                results.append((region, text, conf))
        finally:
            doc.close()
        return results

    def _run_parallel(self) -> List[Tuple[RegionRef, str, Optional[float]]]:
        total = len(self.regions)
        results: List[Optional[Tuple[RegionRef, str, Optional[float]]]] = [None] * total
        max_workers = _max_parallel_workers(total)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx: Dict[Future, int] = {
                executor.submit(
                    _run_ocr_standalone, self.doc_path, region.page, region.rect,
                    self.dpi_high, self.rotation, self.engine, self.lang, self.table_mode,
                ): idx
                for idx, region in enumerate(self.regions)
            }
            done_count = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                region = self.regions[idx]
                done_count += 1
                try:
                    text, conf = future.result()
                except Exception as e:
                    text, conf = f"[Lỗi ở vùng #{region.id}: {e}]", None
                results[idx] = (region, text, conf)
                self.progress.emit(
                    f"[Song song] Đã xong {done_count}/{total} — vùng #{region.id} (Trang {region.page + 1})..."
                )

        # Ghép lại kết quả TRẢ VỀ THEO ĐÚNG THỨ TỰ GỐC (giống hệt chế độ tuần
        # tự) — không phụ thuộc thứ tự thực tế hoàn thành song song.
        return [r for r in results if r is not None]

    @staticmethod
    def _build_confidence_summary(results: List[Tuple[RegionRef, str, Optional[float]]], multi: bool) -> str:
        if not results:
            return ""
        if not multi:
            return _fmt_conf(results[0][2]) or ""
        parts = []
        for region, _text, conf in results:
            fc = _fmt_conf(conf)
            if fc is not None:
                parts.append(f"#{region.id} (Tr.{region.page + 1}): {fc}")
        return ", ".join(parts)


class BatchOCRWorker(QThread):
    """
    OCR lặp qua NHIỀU trang, áp dụng TOÀN BỘ vùng chọn hiện có (kể cả nhiều
    vùng — multi-region) lên mỗi trang. Trong 1 trang, các vùng nối bằng
    '---'; giữa các trang nối bằng '--- Trang X ---'.

    Hỗ trợ hủy giữa chừng qua request_cancel(): khi bị hủy, worker dừng ngay
    (ở trang đang xử lý, hoặc — nếu đang chạy song song — hủy các tác vụ
    CHƯA bắt đầu và bỏ qua kết quả) và KHÔNG emit kết quả (mất toàn bộ kết
    quả đã OCR được cho tới lúc đó) — theo yêu cầu tối ưu code, không cần
    lưu partial results.

    finished_ok(text, confidence_summary, confidences_by_seq): tham số thứ
    3 LUÔN là dict rỗng ở worker này (không có vùng chọn "thật" nào được lưu
    lại trên các trang khác để tô màu lại trên canvas — xem PDFViewer,
    "Extract tất cả trang" chỉ dùng vùng ở trang hiện tại làm MẪU áp lên mọi
    trang, không tạo entry chọn vùng thật cho các trang đó).
    """

    progress = Signal(str)
    finished_ok = Signal(str, str, dict)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, doc_path, page_numbers: List[int], clip_rects: List, dpi_high, lang, engine, rotation=0,
                 table_mode: Optional[str] = None, parallel: bool = False, parent=None):
        super().__init__(parent)
        self.doc_path = doc_path
        self.page_numbers = page_numbers
        self.clip_rects = clip_rects
        self.dpi_high = dpi_high
        self.lang = lang
        self.engine = engine
        self.rotation = rotation
        self.table_mode = table_mode
        self._cancel_requested = False
        n_tasks = len(page_numbers) * max(1, len(clip_rects))
        self.parallel = bool(parallel) and getattr(engine, "name", "") == "tesseract" and n_tasks > 1

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            outcome = self._run_parallel() if self.parallel else self._run_sequential()
            if outcome is None:  # bị hủy giữa chừng
                self.cancelled.emit()
                return
            combined_text, confidence_summary = outcome
            self.finished_ok.emit(combined_text, confidence_summary, {})
        except Exception as e:
            self.failed.emit(str(e))

    def _run_sequential(self) -> Optional[Tuple[str, str]]:
        doc = fitz.open(self.doc_path)
        page_blocks = []
        conf_parts: List[str] = []
        total = len(self.page_numbers)
        multi_region = len(self.clip_rects) > 1
        try:
            for i, page_no in enumerate(self.page_numbers, start=1):
                if self._cancel_requested:
                    return None

                self.progress.emit(f"Đang OCR trang {page_no + 1} ({i}/{total})...")
                page = doc[page_no]
                texts = []
                for r_idx, clip_rect in enumerate(self.clip_rects, start=1):
                    try:
                        text, conf = _run_ocr_on_clip(
                            page, clip_rect, self.dpi_high, self.rotation, self.engine, self.lang, self.table_mode
                        )
                    except Exception as region_err:
                        text, conf = f"[Lỗi ở trang {page_no + 1}: {region_err}]", None
                    texts.append(text)
                    fc = _fmt_conf(conf)
                    if fc is not None:
                        label = f"Trang {page_no + 1} (Vùng {r_idx})" if multi_region else f"Trang {page_no + 1}"
                        conf_parts.append(f"{label}: {fc}")

                page_text = "\n---\n".join(texts)
                page_blocks.append(f"--- Trang {page_no + 1} ---\n{page_text}")
        finally:
            doc.close()

        if self._cancel_requested:
            return None
        return "\n\n".join(page_blocks), ", ".join(conf_parts)

    def _run_parallel(self) -> Optional[Tuple[str, str]]:
        # Mỗi tác vụ = (trang, vùng) — làm phẳng ra để tận dụng tối đa số
        # nhân CPU, kể cả khi mỗi trang chỉ có 1 vùng (trường hợp phổ biến
        # nhất) thì vẫn song song hóa được GIỮA các trang với nhau.
        tasks = [
            (page_no, r_idx, clip_rect)
            for page_no in self.page_numbers
            for r_idx, clip_rect in enumerate(self.clip_rects, start=1)
        ]
        total = len(tasks)
        multi_region = len(self.clip_rects) > 1
        max_workers = _max_parallel_workers(total)

        # kết quả[(page_no, r_idx)] = (text, conf) — ghép lại theo đúng thứ
        # tự gốc sau khi xong, KHÔNG phụ thuộc thứ tự hoàn thành thực tế.
        results: Dict[Tuple[int, int], Tuple[str, Optional[float]]] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task: Dict[Future, Tuple[int, int]] = {
                executor.submit(
                    _run_ocr_standalone, self.doc_path, page_no, clip_rect,
                    self.dpi_high, self.rotation, self.engine, self.lang, self.table_mode,
                ): (page_no, r_idx)
                for page_no, r_idx, clip_rect in tasks
            }

            done_count = 0
            for future in as_completed(future_to_task):
                if self._cancel_requested:
                    # Hủy các tác vụ CHƯA kịp bắt đầu (future.cancel() chỉ có
                    # tác dụng với tác vụ chưa chạy) — tác vụ đang chạy dở sẽ
                    # tự hoàn tất nhưng kết quả của cả lượt này sẽ bị bỏ qua.
                    for f in future_to_task:
                        f.cancel()
                    return None

                page_no, r_idx = future_to_task[future]
                done_count += 1
                try:
                    text, conf = future.result()
                except Exception as e:
                    text, conf = f"[Lỗi ở trang {page_no + 1}: {e}]", None
                results[(page_no, r_idx)] = (text, conf)
                self.progress.emit(f"[Song song] Đã xong {done_count}/{total} (trang/vùng)...")

        if self._cancel_requested:
            return None

        page_blocks = []
        conf_parts: List[str] = []
        for page_no in self.page_numbers:
            texts = []
            for r_idx in range(1, len(self.clip_rects) + 1):
                text, conf = results.get((page_no, r_idx), ("", None))
                texts.append(text)
                fc = _fmt_conf(conf)
                if fc is not None:
                    label = f"Trang {page_no + 1} (Vùng {r_idx})" if multi_region else f"Trang {page_no + 1}"
                    conf_parts.append(f"{label}: {fc}")
            page_text = "\n---\n".join(texts)
            page_blocks.append(f"--- Trang {page_no + 1} ---\n{page_text}")

        return "\n\n".join(page_blocks), ", ".join(conf_parts)
