from __future__ import annotations

from typing import NamedTuple

import fitz


class RegionRef(NamedTuple):
    """1 vùng chọn CỤ THỂ đã vẽ trên PDF (có thể ở bất kỳ trang nào).

    - id   : số thứ tự HIỂN THỊ theo đúng thứ tự vẽ (không reset khi đổi
             trang) — dùng để hiển thị nhãn "#<id>" trên canvas và trong kết
             quả OCR. Số này CÓ THỂ bị renumber (đổi giá trị) nếu người dùng
             thêm/xóa vùng khác trong lúc OCR đang chạy nền — KHÔNG dùng để
             map ngược kết quả bất đồng bộ (dùng `seq` cho việc đó).
    - seq  : ID BẤT BIẾN (thứ tự vẽ nội bộ, không đổi, không hiển thị) — dùng
             để map chính xác confidence/kết quả trả về (bất đồng bộ, từ
             background thread) về đúng vùng chọn, kể cả khi `id` đã bị
             renumber trong lúc chờ OCR chạy xong.
    - page : số trang (0-based) — trang mà vùng này được vẽ trên đó.
    - rect : vị trí vùng chọn trong không gian PAGE (points của PDF) — độc
             lập với DPI/zoom hiển thị, dùng để render lại ở DPI cao khi OCR.
    """

    id: int
    seq: int
    page: int
    rect: "fitz.Rect"

CONFIDENCE_RED_THRESHOLD = 60.0
CONFIDENCE_YELLOW_THRESHOLD = 85.0
