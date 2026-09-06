from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .ocr_worker import BatchOCRWorker, EngineInitWorker, MultiRegionOCRWorker
from .output_panel import OutputPanel
from .pdf_viewer import PDFViewer

LANGUAGES = {
    "Tiếng Việt": "vie",
    "English": "eng",
    "Việt + Eng": "vie+eng",
}

ENGINES = {
    "Tesseract": "tesseract",
    "PaddleOCR": "paddleocr",
}
DEFAULT_ENGINE_LABEL = "Tesseract"

# None = OCR text thường. "heuristic" = dựng bảng từ box từ/dòng (engine nào
# cũng dùng được). "pp_structure" = model chuyên bảng, CHỈ dùng được khi đang
# chọn engine PaddleOCR.
TABLE_MODES = {
    "Off": None,
    "Table (Heuristic — light)": "heuristic",
    "Table (PP-Structure — Paddle, advance)": "pp_structure",
}
DEFAULT_TABLE_MODE_LABEL = "Off"

APP_TITLE = "OCR2Txt v1.3 - Vibed by TwentySeV"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 750)
        self.setAcceptDrops(True)

        self._engine_name = ENGINES[DEFAULT_ENGINE_LABEL]
        self._engine = None
        self._engine_init_worker = None  # EngineInitWorker đang chạy (nếu có) — tránh chồng lấn khi đổi engine liên tục
        self._worker = None  # MultiRegionOCRWorker/BatchOCRWorker đang chạy (nếu có)

        self._build_ui()
        self._connect_signals()
        self._init_engine()

    # ==================== UI ====================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # ---------- PDF Viewer ----------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.viewer = PDFViewer()
        left_layout.addWidget(self.viewer, 1)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Ngôn ngữ:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        options_row.addWidget(self.lang_combo)

        options_row.addSpacing(8)
        options_row.addWidget(QLabel("Engine:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(ENGINES.keys())
        self.engine_combo.setCurrentText(DEFAULT_ENGINE_LABEL)
        options_row.addWidget(self.engine_combo)

        options_row.addSpacing(8)
        options_row.addWidget(QLabel("Table:"))
        self.table_combo = QComboBox()
        self.table_combo.addItems(TABLE_MODES.keys())
        self.table_combo.setCurrentText(DEFAULT_TABLE_MODE_LABEL)
        self.table_combo.setToolTip(
            "Heuristic: Dựng bảng từ vị trí từ/dòng, dùng được với cả 2 engine.\n"
            "PP-Structure: Model chuyên bảng, chính xác hơn nhưng chỉ dùng được với engine PaddleOCR."
        )
        options_row.addWidget(self.table_combo)

        options_row.addSpacing(8)
        self.parallel_checkbox = QCheckBox("Chạy song song (beta)")
        self.parallel_checkbox.setChecked(False)  # mặc định TẮT — giữ nguyên hành vi tuần tự đã ổn định
        self.parallel_checkbox.setToolTip(
            "Chỉ có tác dụng khi Engine = Tesseract VÀ có từ 2 vùng/trang trở lên.\n"
            "OCR nhiều vùng/trang cùng lúc bằng nhiều luồng — nhanh hơn trên máy nhiều nhân,\n"
            "kết quả (thứ tự, nội dung) giống hệt chế độ tuần tự, chỉ khác tốc độ.\n"
            "PaddleOCR luôn chạy tuần tự (không hỗ trợ chạy đồng thời an toàn)."
        )
        options_row.addWidget(self.parallel_checkbox)
        options_row.addStretch()
        left_layout.addLayout(options_row)

        extract_row = QHBoxLayout()
        self.extract_btn = QPushButton("Extract")
        self.extract_btn.setEnabled(False)
        self.extract_btn.setToolTip(
            "OCR TẤT CẢ vùng chọn đã đánh dấu, ở MỌI trang (kể cả khi đã đánh dấu vùng\n"
            "trên nhiều trang khác nhau) — mỗi vùng OCR đúng trên trang riêng của nó.\n"
            "Hoặc nhấn Enter khi đang thao tác trên trang PDF."
        )
        extract_row.addWidget(self.extract_btn)

        self.apply_all_btn = QPushButton("Extract tất cả trang")
        self.apply_all_btn.setEnabled(False)
        self.apply_all_btn.setToolTip(
            "Dùng vùng chọn ở TRANG ĐANG XEM làm mẫu, OCR đúng vị trí đó trên MỌI trang\n"
            "của file (vùng đã đánh dấu ở trang khác không liên quan tới nút này)."
        )
        extract_row.addWidget(self.apply_all_btn)

        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.setVisible(False)
        extract_row.addWidget(self.cancel_btn)

        extract_row.addStretch()
        left_layout.addLayout(extract_row)

        page_row = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.page_label = QLabel("0 / 0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setMinimumWidth(70)
        self.next_btn = QPushButton("▶")
        self.rotate_btn = QPushButton("⟳ Xoay")

        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Page")
        self.page_input.setFixedWidth(60)
        self.page_input.setValidator(QIntValidator(1, 999999))
        self.page_input.setToolTip("Nhập số trang rồi nhấn Enter để nhảy tới")

        page_row.addWidget(self.prev_btn)
        page_row.addWidget(self.page_label)
        page_row.addWidget(self.next_btn)
        page_row.addWidget(self.rotate_btn)
        page_row.addSpacing(12)
        page_row.addWidget(QLabel("Jump to:"))
        page_row.addWidget(self.page_input)
        page_row.addStretch()
        left_layout.addLayout(page_row)

        splitter.addWidget(left)

        # ---------- Output ----------
        self.output_panel = OutputPanel()
        splitter.addWidget(self.output_panel)
        splitter.setSizes([760, 440])

        # ---------- Loading/progress/error ----------
        status_row = QHBoxLayout()
        self.status_label = QLabel("Đang khởi tạo...")
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate (spinner)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(160)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.progress_bar)
        root.addLayout(status_row)

        # ---------- Mở file + Zoom ----------
        zoom_row = QHBoxLayout()
        self.open_btn = QPushButton("Open PDF...")
        zoom_row.addWidget(self.open_btn)
        zoom_row.addStretch()

        self.zoom_out_btn = QPushButton("Zoom -")
        self.zoom_input = QLineEdit("100")
        self.zoom_input.setFixedWidth(50)
        self.zoom_input.setValidator(QIntValidator(20, 600))
        self.zoom_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_input.setToolTip("Input zoom (%) rồi Enter")
        self.zoom_in_btn = QPushButton("Zoom +")
        zoom_row.addWidget(self.zoom_out_btn)
        zoom_row.addWidget(self.zoom_input)
        zoom_row.addWidget(QLabel("%"))
        zoom_row.addWidget(self.zoom_in_btn)
        root.addLayout(zoom_row)

    def _connect_signals(self):
        self.open_btn.clicked.connect(self.open_pdf_dialog)
        self.prev_btn.clicked.connect(self.viewer.prev_page)
        self.next_btn.clicked.connect(self.viewer.next_page)
        self.rotate_btn.clicked.connect(self._on_rotate_clicked)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.page_input.returnPressed.connect(self._jump_to_page_input)
        self.zoom_input.returnPressed.connect(self._apply_zoom_input)

        self.extract_btn.clicked.connect(self.extract_current_selection)
        self.apply_all_btn.clicked.connect(self.extract_all_pages)
        self.cancel_btn.clicked.connect(self._cancel_batch)
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)

        self.viewer.page_changed.connect(self._on_page_changed)
        self.viewer.selection_changed.connect(self._on_selection_changed)
        self.viewer.extract_requested.connect(self.extract_current_selection)

    # ==================== Drag & drop ====================
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self._load_pdf(path)
                return

    # ==================== PDF loading ====================
    def open_pdf_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
        if path:
            self._load_pdf(path)

    def _load_pdf(self, path: str):
        if not self.viewer.load_pdf(path):
            QMessageBox.critical(self, "Lỗi", "Không thể mở file PDF này.")
            return
        self.setWindowTitle(f"{APP_TITLE} — {os.path.basename(path)}")
        self.status_label.setText(f"Đã mở: {os.path.basename(path)} ({self.viewer.page_count} trang)")
        self._refresh_extract_buttons()
        self.zoom_input.setText(str(self.viewer.zoom_percent()))
        self.page_input.clear()

    # ==================== OCR engine ====================
    def _init_engine(self):
        if self._engine_init_worker is not None:
            return  # đã có 1 lượt khởi tạo đang chạy — không chồng lấn
        self.status_label.setText(f"Đang khởi tạo OCR engine ({self._engine_name})...")
        self.progress_bar.setVisible(True)
        self._set_controls_enabled(False)
        self._refresh_extract_buttons()

        worker = EngineInitWorker(self._engine_name)
        worker.finished_ok.connect(self._on_engine_ready)
        worker.failed.connect(self._on_engine_init_failed)
        self._engine_init_worker = worker
        worker.start()

    def _on_engine_ready(self, engine):
        self._engine = engine
        self._engine_init_worker = None
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ready. Kéo & thả file PDF vào đây hoặc bấm “Open PDF...”.")
        self._set_controls_enabled(True)
        self._refresh_extract_buttons()

    def _on_engine_init_failed(self, err: str):
        self._engine = None
        self._engine_init_worker = None
        self.progress_bar.setVisible(False)
        self.status_label.setText("Lỗi khởi tạo OCR engine.")
        self._set_controls_enabled(True)
        self._refresh_extract_buttons()
        QMessageBox.warning(
            self,
            "Không khởi tạo được OCR engine",
            f"{err}\n\nBạn vẫn có thể xem PDF, nhưng chưa Extract được cho tới khi engine sẵn sàng.",
        )

    def _on_engine_changed(self, label: str):
        if self._worker is not None or self._engine_init_worker is not None:
            self.engine_combo.blockSignals(True)
            self.engine_combo.setCurrentText(
                next(k for k, v in ENGINES.items() if v == self._engine_name)
            )
            self.engine_combo.blockSignals(False)
            return
        new_name = ENGINES[label]
        if new_name == self._engine_name and self._engine is not None:
            return
        self._engine_name = new_name
        self._engine = None
        self._init_engine()

    # ==================== View controls ====================
    def _zoom_in(self):
        self.viewer.zoom_in()
        self.zoom_input.setText(str(self.viewer.zoom_percent()))

    def _zoom_out(self):
        self.viewer.zoom_out()
        self.zoom_input.setText(str(self.viewer.zoom_percent()))

    def _apply_zoom_input(self):
        text = self.zoom_input.text().strip()
        if not text:
            return
        try:
            percent = int(text)
        except ValueError:
            self.zoom_input.setText(str(self.viewer.zoom_percent()))
            return
        self.viewer.set_zoom_percent(percent)
        self.zoom_input.setText(str(self.viewer.zoom_percent()))
        self.viewer.setFocus()

    def _jump_to_page_input(self):
        text = self.page_input.text().strip()
        if not text or not self.viewer.doc:
            return
        try:
            page_no = int(text)
        except ValueError:
            self.page_input.clear()
            return
        self.viewer.goto_page(page_no - 1)  # UI 1-based -> index 0-based
        self.page_input.clear()
        self.viewer.setFocus()

    def _on_rotate_clicked(self):
        # Xoay trang xóa TOÀN BỘ vùng chọn đang có (ở mọi trang) — xem lý do
        # trong PDFViewer.rotate_page(). Hỏi xác nhận trước nếu đang có vùng
        # chọn để tránh mất công đánh dấu ngoài ý muốn.
        if self.viewer.has_selection():
            reply = QMessageBox.question(
                self,
                "Xác nhận xoay trang",
                f"Đang có {self.viewer.selection_count} vùng chọn (ở một hoặc nhiều trang).\n"
                "Xoay trang sẽ XÓA TOÀN BỘ các vùng chọn này. Tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.viewer.rotate_page(90)

    def _on_page_changed(self, current: int, total: int):
        self.page_label.setText(f"{current} / {total}")
        self._refresh_extract_buttons()

    def _on_selection_changed(self, has_selection: bool):
        self._refresh_extract_buttons()

    def _refresh_extract_buttons(self):
        busy = self._worker is not None or self._engine_init_worker is not None
        engine_ready = self._engine is not None
        self.extract_btn.setEnabled(self.viewer.has_selection() and not busy and engine_ready)
        self.apply_all_btn.setEnabled(self.viewer.has_current_page_selection() and not busy and engine_ready)

    # ==================== Table mode helpers ====================
    def _current_table_mode(self):
        return TABLE_MODES[self.table_combo.currentText()]

    def _check_table_mode_supported(self) -> bool:
        table_mode = self._current_table_mode()
        if table_mode == "pp_structure" and self._engine_name != "paddleocr":
            QMessageBox.warning(
                self,
                "Không hỗ trợ",
                "Chế độ Table 'PP-Structure' chỉ dùng được với engine PaddleOCR.\n"
                "Hãy đổi Engine sang PaddleOCR, hoặc chọn Table 'Heuristic'.",
            )
            return False
        return True

    # ==================== Extraction ====================
    def extract_current_selection(self):
        """OCR TẤT CẢ vùng chọn đã đánh dấu, ở MỌI trang (cross-page)."""
        if self._worker is not None:
            return
        if self._engine is None:
            QMessageBox.warning(self, "Not Ready", "OCR engine chưa được khởi tạo thành công.")
            return
        regions = self.viewer.get_all_selection_regions()
        if not regions:
            return
        if not self._check_table_mode_supported():
            return

        lang = LANGUAGES[self.lang_combo.currentText()]
        worker = MultiRegionOCRWorker(
            doc_path=self.viewer.doc_path,
            regions=regions,
            dpi_high=PDFViewer.HIGH_DPI,
            lang=lang,
            engine=self._engine,
            rotation=self.viewer.rotation,
            table_mode=self._current_table_mode(),
            parallel=self.parallel_checkbox.isChecked(),
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_extract_done)
        worker.failed.connect(self._on_extract_failed)
        self._worker = worker
        self._set_busy(True, "Đang xử lý OCR...")
        worker.start()

    def extract_all_pages(self):
        """Dùng vùng chọn ở TRANG ĐANG XEM làm mẫu, OCR lặp lại trên mọi trang."""
        if self._worker is not None:
            return
        if self._engine is None:
            QMessageBox.warning(self, "Note Ready", "OCR engine chưa được khởi tạo thành công.")
            return
        clip_rects = self.viewer.get_current_page_selection_rects()
        if not clip_rects:
            return
        if not self._check_table_mode_supported():
            return

        lang = LANGUAGES[self.lang_combo.currentText()]
        page_numbers = list(range(self.viewer.page_count))
        worker = BatchOCRWorker(
            doc_path=self.viewer.doc_path,
            page_numbers=page_numbers,
            clip_rects=clip_rects,
            dpi_high=PDFViewer.HIGH_DPI,
            lang=lang,
            engine=self._engine,
            rotation=self.viewer.rotation,
            table_mode=self._current_table_mode(),
            parallel=self.parallel_checkbox.isChecked(),
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_extract_done)
        worker.failed.connect(self._on_extract_failed)
        worker.cancelled.connect(self._on_batch_cancelled)
        self._worker = worker
        self._set_busy(True, "Đang OCR hàng loạt...")
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)
        worker.start()

    def _cancel_batch(self):
        if isinstance(self._worker, BatchOCRWorker):
            self._worker.request_cancel()
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Đang hủy...")

    # ==================== Worker callbacks ====================
    def _on_progress(self, msg: str):
        self.status_label.setText(msg)

    def _on_extract_done(self, text: str, confidence_summary: str, confidences_by_seq: dict):
        self.output_panel.append_text(text)
        if confidences_by_seq:
            self.viewer.apply_region_confidences(confidences_by_seq)
        message = "Done."
        if confidence_summary:
            message += f" Độ tin cậy: {confidence_summary}"
        self.cancel_btn.setVisible(False)
        self._worker = None
        self._set_busy(False, message)
        self.status_label.setToolTip(message)

    def _on_extract_failed(self, err: str):
        QMessageBox.critical(self, "Lỗi OCR", err)
        self.cancel_btn.setVisible(False)
        self._worker = None
        self._set_busy(False, "Có lỗi xảy ra trong quá trình OCR.")

    def _on_batch_cancelled(self):
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(True)
        self._worker = None
        self._set_busy(False, "Đã hủy Extract tất cả trang.")

    def _set_busy(self, busy: bool, message: str = ""):
        self.progress_bar.setVisible(busy)
        self.open_btn.setEnabled(not busy)
        self._set_controls_enabled(not busy)
        self._refresh_extract_buttons()
        if message:
            self.status_label.setText(message)

    def _set_controls_enabled(self, enabled: bool):
        self.engine_combo.setEnabled(enabled)
        self.lang_combo.setEnabled(enabled)
        self.table_combo.setEnabled(enabled)
        self.parallel_checkbox.setEnabled(enabled)

    # ==================== Cleanup ====================
    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            if isinstance(self._worker, BatchOCRWorker):
                self._worker.request_cancel()
            self._worker.wait(2000)
        if self._engine_init_worker is not None and self._engine_init_worker.isRunning():
            self._engine_init_worker.wait(2000)
        if self.viewer.doc:
            self.viewer.doc.close()
        super().closeEvent(event)
