"""
Hậu xử lý text sau khi OCR xong (rất nhẹ, chạy ngay trong worker OCR đang
chạy nền — không cần thread riêng).
"""
from __future__ import annotations

import re

# Chỉ khớp dấu "." đứng MỘT MÌNH ở đầu dòng (thường là bullet điểm bị scan
# lỗi từ dấu gạch đầu dòng "-"), theo sau bởi khoảng trắng hoặc hết dòng.
# Không đụng tới dấu chấm câu/số thập phân ở giữa/cuối câu.
_LEADING_DOT_BULLET_RE = re.compile(r"(?m)^(\s*)\.(\s+|$)")


def fix_bullet_dots(text: str) -> str:
    """Thay '.' ở đầu dòng (bullet bị scan lỗi) bằng '-'."""
    if not text:
        return text
    return _LEADING_DOT_BULLET_RE.sub(lambda m: f"{m.group(1)}-{m.group(2)}", text)


def postprocess_text(text: str) -> str:
    """Điểm vào duy nhất cho toàn bộ bước hậu xử lý text."""
    return fix_bullet_dots(text)
