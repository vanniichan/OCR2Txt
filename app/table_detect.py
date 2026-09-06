"""
Table detection.

Hai chế độ:
  - Heuristic (engine-agnostic): dựng bảng markdown từ danh sách từ/dòng kèm
    bounding box (ocr_engine.BaseOCREngine.recognize_words()) bằng cách gom
    cụm theo hàng (y gần nhau) rồi theo cột (x gần nhau) — không cần model
    riêng, chạy nhanh, nhưng chỉ chính xác với bảng có hàng/cột thẳng, không
    merge cell.
  - PP-Structure (chỉ PaddleOCR): model chuyên nhận diện cấu trúc bảng, trả
    thẳng ra HTML — hàm html_table_to_markdown() ở đây dùng để convert output
    đó sang markdown cho đồng nhất với chế độ heuristic.
"""
from __future__ import annotations

import re
from typing import List

from .ocr_engine import WordBox


def _cluster_1d(values: List[float], gap_ratio: float = 0.6, min_gap: float = 4.0) -> List[List[int]]:
    """Gom cụm các giá trị 1 chiều (đã có index gốc) thành các nhóm gần nhau.

    Trả về list các cụm, mỗi cụm là list index (vào mảng values gốc), đã sắp
    theo thứ tự giá trị tăng dần. Ngưỡng tách cụm = median khoảng cách giữa
    các điểm liên tiếp * gap_ratio (tối thiểu min_gap) — thích ứng với cỡ chữ
    to/nhỏ thay vì dùng 1 số cố định.
    """
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    if len(order) == 1:
        return [order]

    diffs = [values[order[i + 1]] - values[order[i]] for i in range(len(order) - 1)]
    diffs_sorted = sorted(diffs)
    median_diff = diffs_sorted[len(diffs_sorted) // 2] if diffs_sorted else min_gap
    threshold = max(median_diff * gap_ratio, min_gap)

    clusters: List[List[int]] = [[order[0]]]
    for i in range(1, len(order)):
        idx = order[i]
        prev_idx = order[i - 1]
        if values[idx] - values[prev_idx] <= threshold:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])
    return clusters


def words_to_markdown_table(words: List[WordBox]) -> str:
    """Dựng bảng markdown từ danh sách WordBox (text, conf, box=(x0,y0,x1,y1))."""
    if not words:
        return ""

    # --- Gom hàng: theo tâm y ---
    y_centers = [(w["box"][1] + w["box"][3]) / 2 for w in words]
    heights = [w["box"][3] - w["box"][1] for w in words]
    median_h = sorted(heights)[len(heights) // 2] if heights else 10
    row_clusters = _cluster_1d(y_centers, gap_ratio=0.6, min_gap=max(median_h * 0.5, 4.0))
    # Mỗi cụm là 1 hàng — sắp các hàng theo y tăng dần (đã đúng thứ tự do _cluster_1d trả theo order tăng dần)

    # --- Xác định cột: gom tâm x của TẤT CẢ từ (toàn bảng) để lấy biên cột chung ---
    x_centers = [(w["box"][0] + w["box"][2]) / 2 for w in words]
    widths = [w["box"][2] - w["box"][0] for w in words]
    median_w = sorted(widths)[len(widths) // 2] if widths else 20
    col_clusters = _cluster_1d(x_centers, gap_ratio=0.75, min_gap=max(median_w * 1.2, 15.0))
    # col_clusters: list cụm index (vào mảng words) theo x tăng dần -> đây chính là các CỘT
    col_order = list(range(len(col_clusters)))  # thứ tự cột theo x tăng dần (đã đúng thứ tự)

    def col_index_of(word_idx: int) -> int:
        for ci, cluster in enumerate(col_clusters):
            if word_idx in cluster:
                return ci
        return -1

    n_cols = len(col_clusters)
    rows_text: List[List[str]] = []
    for row_cluster in row_clusters:
        # Trong 1 hàng, gom các từ theo đúng cột đã xác định ở trên, ghép nếu
        # nhiều từ rơi vào cùng 1 ô (cùng hàng + cùng cột) theo thứ tự x.
        cells = ["" for _ in range(n_cols)]
        row_word_idxs = sorted(row_cluster, key=lambda i: x_centers[i])
        for wi in row_word_idxs:
            ci = col_index_of(wi)
            if ci < 0:
                continue
            text = words[wi]["text"]
            cells[ci] = f"{cells[ci]} {text}".strip() if cells[ci] else text
        rows_text.append(cells)

    if not rows_text or n_cols == 0:
        return ""

    header, *data_rows = rows_text
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * n_cols) + "|")
    for row in data_rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def html_table_to_markdown(html: str) -> str:
    """Convert HTML bảng (output của PP-Structure) sang markdown đơn giản.

    Không xử lý đầy đủ rowspan/colspan (chỉ lặp lại nội dung nếu có merge) —
    đủ dùng để xuất text đọc được, không nhằm tái tạo layout HTML 100%.
    """
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    cell_re = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
    tag_re = re.compile(r"<[^>]+>")

    rows = []
    for row_match in row_re.findall(html):
        cells = [tag_re.sub("", c).strip() for c in cell_re.findall(row_match)]
        cells = [re.sub(r"\s+", " ", c) for c in cells]
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    n_cols = max(len(r) for r in rows)
    rows = [r + [""] * (n_cols - len(r)) for r in rows]

    header, *data_rows = rows
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * n_cols) + "|")
    for row in data_rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
