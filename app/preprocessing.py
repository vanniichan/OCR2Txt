"""
Preprocessing ảnh (OpenCV) cho vùng OCR đã chọn.

Nguyên tắc: chỉ preprocess đúng vùng đã crop (không preprocess cả trang),
và chỉ chạy khi người dùng bấm [Extract] — không chạy sẵn.
"""
from __future__ import annotations

import cv2
import numpy as np


def preprocess_image(
    image: np.ndarray,
    deskew: bool = True,
    binarize: bool = True,
    denoise: bool = True,
) -> np.ndarray:
    """
    Nhận ảnh RGB/BGR hoặc grayscale (numpy array), trả về ảnh đã (tùy chọn)
    khử nhiễu, tăng tương phản, và (tùy chọn) deskew — sẵn sàng để OCR.

    binarize=True  -> nhị phân hóa cứng (adaptive threshold). Phù hợp Tesseract.
    binarize=False -> giữ ảnh xám, chỉ tăng tương phản nhẹ (CLAHE). Phù hợp các
                       engine deep-learning (PaddleOCR) vốn tự học đặc trưng tốt
                       hơn trên ảnh xám, nhị phân cứng đôi khi làm mất chi tiết
                       ký tự nhỏ (dấu gạch, dấu câu...).
    denoise=True   -> CHO PHÉP khử nhiễu khi cần (mặc định) — nhưng việc có
                       thực sự chạy fastNlMeansDenoising (bước tốn thời gian
                       nhất trong preprocessing) hay không do
                       _needs_denoising() TỰ ĐỘNG quyết định dựa trên mức
                       nhiễu đo được của từng ảnh cụ thể (xem hàm đó): ảnh
                       scan có nhiễu hạt/ố giấy vẫn được khử nhiễu ĐẦY ĐỦ y
                       hệt hành vi cũ (không giảm chất lượng); chỉ bỏ qua khi
                       ảnh đo được đã rất sạch (PDF gốc kỹ thuật số) — giúp
                       tăng tốc đáng kể khi Extract hàng loạt nhiều trang mà
                       không cần người dùng tự khai báo loại PDF.
    denoise=False  -> luôn bỏ qua bước khử nhiễu, bất kể mức nhiễu đo được
                       (dùng khi cần ép buộc/kiểm thử).
    """
    if image is None or image.size == 0:
        raise ValueError("Ảnh vùng chọn rỗng, không thể preprocess.")

    if image.ndim == 3:
        # PyMuPDF trả pixmap dạng RGB
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image

    if denoise and _needs_denoising(gray):
        # Khử nhiễu nhẹ, giữ nét chữ
        base = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
    else:
        base = gray

    if binarize:
        # Threshold thích nghi — chịu được ánh sáng/nền không đều tốt hơn threshold cố định
        result = cv2.adaptiveThreshold(
            base,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,
            C=15,
        )
    else:
        # Chỉ tăng tương phản cục bộ, không ép nhị phân
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        result = clahe.apply(base)

    if deskew:
        result = _deskew(result)

    return result


# Ngưỡng cố ý đặt THẤP (thiên về "vẫn denoise nếu còn nghi ngờ") — chỉ ảnh
# thực sự rất sạch (chênh lệch trung bình so với bản median-blur gần như
# bằng 0, đúng kiểu render từ PDF digital-born) mới được coi là không cần
# khử nhiễu. Bất kỳ dấu hiệu hạt nhiễu/ố giấy nào từ bản scan đều sẽ vượt
# ngưỡng này và vẫn được denoise đầy đủ như hành vi cũ.
_NOISE_SKIP_THRESHOLD = 1.2


def _needs_denoising(gray: np.ndarray) -> bool:
    """Đo nhanh mức nhiễu bằng median-blur (rẻ hơn NHIỀU so với chính
    fastNlMeansDenoising) để quyết định có cần chạy bước khử nhiễu đầy đủ
    hay không. Trả về True (cần denoise) trong mọi trường hợp mơ hồ/lỗi —
    an toàn theo hướng KHÔNG BAO GIỜ giảm chất lượng so với hành vi cũ."""
    try:
        blurred = cv2.medianBlur(gray, 3)
        diff = cv2.absdiff(gray, blurred)
        noise_level = float(np.mean(diff))
        return noise_level > _NOISE_SKIP_THRESHOLD
    except Exception:
        return True


def _deskew(img: np.ndarray) -> np.ndarray:
    """
    Ước lượng góc nghiêng của vùng chữ và xoay lại cho thẳng.
    Dùng Otsu threshold nội bộ để ước lượng góc (không phụ thuộc ảnh đầu vào
    đã nhị phân hay còn là ảnh xám), sau đó xoay ảnh gốc (img) theo góc đó.
    """
    _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(bw > 0))
    if coords.shape[0] < 20:
        # Quá ít điểm chữ để ước lượng góc đáng tin cậy -> bỏ qua deskew
        return img

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.1 or abs(angle) > 15:
        # Góc quá nhỏ (không đáng xoay) hoặc quá lớn (khả năng ước lượng sai)
        return img

    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated
