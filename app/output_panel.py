from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class OutputPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("OUTPUT")
        title.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Output OCR sẽ hiển thị ở đây. Bạn có thể edit trực tiếp.")
        layout.addWidget(self.text_edit, 1)

        btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.clear_btn = QPushButton("Clear")
        self.export_btn = QPushButton("Export...")
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.copy_btn.clicked.connect(self.copy_all)
        self.clear_btn.clicked.connect(self.clear_text)
        self.export_btn.clicked.connect(self.export_text)

    # ---------------- API ----------------
    def append_text(self, text: str):
        text = text or "(Không nhận dạng được văn bản)"
        if self.text_edit.toPlainText().strip():
            self.text_edit.append("\n" + text)
        else:
            self.text_edit.setPlainText(text)

    def set_text(self, text: str):
        self.text_edit.setPlainText(text)

    def get_text(self) -> str:
        return self.text_edit.toPlainText()

    def copy_all(self):
        QApplication.clipboard().setText(self.get_text())

    def clear_text(self):
        self.text_edit.clear()

    def export_text(self):
        text = self.get_text()
        if not text.strip():
            QMessageBox.information(self, "Export", "Chưa có nội dung để export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export văn bản",
            "output.txt",
            "Text Files (*.txt);;Word Document (*.docx)",
        )
        if not path:
            return

        try:
            if path.lower().endswith(".docx"):
                self._export_docx(path, text)
            else:
                if not path.lower().endswith(".txt"):
                    path += ".txt"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
        except ImportError:
            QMessageBox.critical(
                self,
                "Thiếu thư viện",
                "Cần cài `python-docx` để export .docx:\n\npip install python-docx",
            )
            return
        except Exception as e:
            QMessageBox.critical(self, "Lỗi Export", str(e))
            return

        QMessageBox.information(self, "Export", f"Đã lưu file:\n{path}")

    @staticmethod
    def _export_docx(path: str, text: str):
        from docx import Document

        doc = Document()
        for line in text.split("\n"):
            doc.add_paragraph(line)
        doc.save(path)
