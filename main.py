"""
OCR2Txt v1.3 - Vibed by TwentySeV — điểm khởi chạy ứng dụng.

Chạy:
    python main.py
"""
import sys

from PySide6.QtWidgets import QApplication

from app.main_window import APP_TITLE, MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
