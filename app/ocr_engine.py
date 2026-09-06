"""
OCR Engine abstraction.

- TesseractEngine: engine MẶC ĐỊNH từ v3 (nhẹ, khởi tạo nhanh — ưu tiên tốc độ
  khởi động), đổi lại độ chính xác thấp hơn PaddleOCR ở một số ký tự/dấu câu.
- PaddleOCREngine: engine TÙY CHỌN (deep-learning, chính xác cao hơn, đặc biệt
  với các ký tự/dấu câu nhỏ như "-"), đổi lại nặng và khởi tạo chậm hơn nhiều
  (đặc biệt lần đầu — có thể phải tải model).

Mỗi engine hỗ trợ 3 chế độ nhận dạng:
  - recognize()          : text thường (kèm confidence 0-100, nếu engine hỗ
                            trợ sẵn; None nếu không có).
  - recognize_words()    : list các "từ/dòng" kèm bounding box + confidence
                            — dùng cho chế độ Table detection (heuristic).
  - recognize_table()    : xuất thẳng bảng markdown bằng model chuyên bảng
                            (hiện chỉ PaddleOCR hỗ trợ qua PP-Structure) —
                            trả về None nếu engine không hỗ trợ.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, TypedDict

import numpy as np


class WordBox(TypedDict):
    text: str
    conf: float  # 0-100
    box: tuple  # (x0, y0, x1, y1) trong không gian pixel của ảnh đưa vào recognize_words()


class BaseOCREngine(ABC):
    name: str = "base"

    @abstractmethod
    def recognize(self, image: np.ndarray, lang: str) -> "tuple[str, Optional[float]]":
        """image: ảnh nhị phân/grayscale (numpy array) đã preprocess.

        Trả về (text, confidence) — confidence là số 0-100 (trung bình các
        dòng/từ nhận dạng được), hoặc None nếu engine không có sẵn confidence
        hoặc không nhận dạng được gì.
        """
        raise NotImplementedError

    def recognize_words(self, image: np.ndarray, lang: str) -> List[WordBox]:
        """Trả về danh sách từ/dòng kèm box + confidence — dùng cho Table
        detection (heuristic). Mặc định: không hỗ trợ (list rỗng)."""
        return []

    def recognize_table(self, image: np.ndarray, lang: str) -> Optional[str]:
        """Trả về bảng dạng markdown (dùng model chuyên bảng, nếu engine hỗ
        trợ), hoặc None nếu không hỗ trợ."""
        return None


class TesseractEngine(BaseOCREngine):
    name = "tesseract"

    # Map lang code nội bộ -> mã ngôn ngữ Tesseract
    LANG_MAP = {
        "vie": "vie",
        "eng": "eng",
        "vie+eng": "vie+eng",
    }

    def __init__(self):
        import pytesseract  # import ở đây để lỗi thiếu binary hiện rõ ràng lúc init

        self._pytesseract = pytesseract
        # Kiểm tra sớm xem tesseract binary có sẵn không (raise nếu thiếu)
        try:
            self._pytesseract.get_tesseract_version()
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Không tìm thấy Tesseract OCR trên máy. Hãy cài Tesseract "
                "(https://github.com/UB-Mannheim/tesseract/wiki với Windows) "
                "và đảm bảo đã thêm vào PATH."
            ) from e

    def recognize(self, image: np.ndarray, lang: str = "vie") -> "tuple[str, Optional[float]]":
        from PIL import Image

        pil_img = Image.fromarray(image)
        tess_lang = self.LANG_MAP.get(lang, lang)
        config = "--oem 3 --psm 6"
        text = self._pytesseract.image_to_string(pil_img, lang=tess_lang, config=config).strip()

        # Gọi thêm image_to_data() (cùng ảnh, cùng config) chỉ để lấy confidence
        # trung bình — không dùng kết quả text của lệnh này (giữ nguyên hành vi
        # text hiện tại của image_to_string).
        confidence = None
        try:
            data = self._pytesseract.image_to_data(
                pil_img, lang=tess_lang, config=config,
                output_type=self._pytesseract.Output.DICT,
            )
            confs = [int(c) for c in data.get("conf", []) if str(c).strip() not in ("", "-1") and int(c) >= 0]
            if confs:
                confidence = sum(confs) / len(confs)
        except Exception:
            confidence = None

        return text, confidence

    def recognize_words(self, image: np.ndarray, lang: str = "vie") -> List[WordBox]:
        from PIL import Image

        pil_img = Image.fromarray(image)
        tess_lang = self.LANG_MAP.get(lang, lang)
        config = "--oem 3 --psm 6"
        try:
            data = self._pytesseract.image_to_data(
                pil_img, lang=tess_lang, config=config,
                output_type=self._pytesseract.Output.DICT,
            )
        except Exception:
            return []

        words: List[WordBox] = []
        n = len(data.get("text", []))
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1
            if conf < 0:
                continue
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            words.append(WordBox(text=text, conf=conf, box=(x, y, x + w, y + h)))
        return words


class PaddleOCREngine(BaseOCREngine):
    """
    Hỗ trợ cả 2 dòng API của thư viện paddleocr:
      - >= 3.0 (mới): PaddleOCR(lang=..., use_textline_orientation=...),
        gọi bằng .predict(image), kết quả là list các object/dict có
        khóa "rec_texts"/"rec_scores"/"rec_boxes"/"rec_polys" (không còn
        use_angle_cls/show_log/.ocr()).
      - < 3.0 (cũ): PaddleOCR(use_angle_cls=True, lang=..., show_log=False),
        gọi bằng .ocr(image, cls=True), kết quả dạng
        [[ [box, (text, score)], ... ]].
    Tự thử API mới trước, nếu lỗi (bản cũ không nhận tham số mới) thì
    fallback sang API cũ — không cần biết trước máy người dùng cài bản nào.
    """

    name = "paddleocr"

    LANG_MAP = {
        "vie": "vi",
        "eng": "en",
        "vie+eng": "vi",  # PaddleOCR không hỗ trợ multi-lang 1 model; ưu tiên vi
    }

    def __init__(self):
        from paddleocr import PaddleOCR  # import nặng, chỉ load khi thực sự chọn engine này

        self._PaddleOCR = PaddleOCR
        self._current_lang = "vi"
        self._ocr = self._create_pipeline(self._current_lang)
        self._table_engine = None  # PP-Structure — lazy init, chỉ tạo khi thực sự dùng Table detection nâng cao

    def _create_pipeline(self, lang: str):
        try:
            # API mới (paddleocr >= 3.0)
            # enable_mkldnn=False: tránh bug đã biết của PaddlePaddle 3.x trên
            # CPU (executor PIR mới lỗi khi convert attribute cho oneDNN/MKL-DNN
            # -> "ConvertPirAttribute2RuntimeAttribute not support ..."). Tắt
            # oneDNN chậm hơn một chút nhưng chạy được ổn định trên mọi máy CPU.
            return self._PaddleOCR(
                lang=lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                enable_mkldnn=False,
            )
        except Exception:
            # Fallback API cũ (paddleocr < 3.0)
            return self._PaddleOCR(use_angle_cls=True, lang=lang, show_log=False, enable_mkldnn=False)

    def _ensure_lang(self, paddle_lang: str):
        if paddle_lang != self._current_lang:
            self._ocr = self._create_pipeline(paddle_lang)
            self._current_lang = paddle_lang

    @staticmethod
    def _to_bgr(image: np.ndarray) -> np.ndarray:
        import cv2

        # Các pipeline của Paddle (nhất là bản >=3.0, dựa trên PaddleX) kỳ
        # vọng ảnh 3 kênh; ảnh preprocess của mình có thể là grayscale 1 kênh.
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image

    def _predict_raw(self, image: np.ndarray, lang: str):
        """Chạy OCR thô, trả về (lines: list[dict(text, score, box)], api: "new"|"old")."""
        paddle_lang = self.LANG_MAP.get(lang, "vi")
        self._ensure_lang(paddle_lang)
        img_for_ocr = self._to_bgr(image)

        lines = []
        if hasattr(self._ocr, "predict"):
            results = self._ocr.predict(img_for_ocr)
            for page in results:
                try:
                    texts = page["rec_texts"]
                    scores = page.get("rec_scores") or []
                    boxes = page.get("rec_boxes")
                    polys = page.get("rec_polys")
                except (TypeError, KeyError):
                    texts = getattr(page, "rec_texts", None) or []
                    scores = getattr(page, "rec_scores", None) or []
                    boxes = getattr(page, "rec_boxes", None)
                    polys = getattr(page, "rec_polys", None)
                for i, text in enumerate(texts or []):
                    score = float(scores[i]) if i < len(scores) else None
                    box = None
                    if boxes is not None and i < len(boxes):
                        b = boxes[i]
                        box = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                    elif polys is not None and i < len(polys):
                        pts = polys[i]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        box = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
                    lines.append({"text": text, "score": score, "box": box})
            return lines, "new"

        # ---- API cũ (paddleocr < 3.0) ----
        result = self._ocr.ocr(img_for_ocr, cls=True)
        if result and result[0]:
            for item in result[0]:
                box_pts, (text, score) = item
                xs = [p[0] for p in box_pts]
                ys = [p[1] for p in box_pts]
                box = (min(xs), min(ys), max(xs), max(ys))
                lines.append({"text": text, "score": float(score), "box": box})
        return lines, "old"

    def recognize(self, image: np.ndarray, lang: str = "vie") -> "tuple[str, Optional[float]]":
        lines, _ = self._predict_raw(image, lang)
        text = "\n".join(l["text"] for l in lines)
        scores = [l["score"] for l in lines if l["score"] is not None]
        confidence = (sum(scores) / len(scores) * 100) if scores else None
        return text, confidence

    def recognize_words(self, image: np.ndarray, lang: str = "vie") -> List[WordBox]:
        lines, _ = self._predict_raw(image, lang)
        words: List[WordBox] = []
        for l in lines:
            if not l["text"] or l["box"] is None:
                continue
            conf = (l["score"] * 100) if l["score"] is not None else 0.0
            words.append(WordBox(text=l["text"], conf=conf, box=l["box"]))
        return words

    def recognize_table(self, image: np.ndarray, lang: str = "vie") -> Optional[str]:
        """Table detection nâng cao qua PP-Structure. Best-effort: API của
        module này thay đổi khá nhiều giữa các bản paddleocr, nên thử lần
        lượt vài class/entrypoint đã biết; nếu không có bản nào dùng được thì
        raise lỗi rõ ràng (KHÔNG âm thầm fallback — người gọi/UI sẽ quyết
        định fallback sang heuristic nếu muốn)."""
        from .table_detect import html_table_to_markdown

        paddle_lang = self.LANG_MAP.get(lang, "vi")
        img_for_ocr = self._to_bgr(image)

        if self._table_engine is None:
            self._table_engine = self._create_table_pipeline(paddle_lang)

        html = self._run_table_pipeline(self._table_engine, img_for_ocr)
        if not html:
            return None
        return html_table_to_markdown(html)

    @staticmethod
    def _create_table_pipeline(lang: str):
        errors = []
        try:
            # paddleocr >= 3.0
            from paddleocr import PPStructureV3

            return PPStructureV3(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
        except Exception as e:
            errors.append(f"PPStructureV3: {e}")
        try:
            # paddleocr < 3.0
            from paddleocr import PPStructure

            return PPStructure(show_log=False, lang=lang, layout=True, table=True, ocr=True)
        except Exception as e:
            errors.append(f"PPStructure: {e}")
        raise RuntimeError(
            "Không khởi tạo được module Table detection (PP-Structure) của "
            "paddleocr trên máy này. Cần bản paddleocr có PPStructureV3 hoặc "
            "PPStructure. Chi tiết: " + " | ".join(errors)
        )

    @staticmethod
    def _run_table_pipeline(table_engine, img_for_ocr) -> Optional[str]:
        # API mới (PPStructureV3.predict) trả list kết quả, mỗi kết quả có thể
        # tra cứu html bảng qua "table_res_list" / "res"... — cấu trúc trả về
        # của PP-Structure không ổn định giữa các bản, nên dò vài đường khả dĩ.
        if hasattr(table_engine, "predict"):
            results = table_engine.predict(img_for_ocr)
            for page in results:
                html = PaddleOCREngine._find_table_html(page)
                if html:
                    return html
            return None

        # API cũ (PPStructure.__call__)
        results = table_engine(img_for_ocr)
        for item in results or []:
            if isinstance(item, dict) and item.get("type") == "table":
                html = (item.get("res") or {}).get("html")
                if html:
                    return html
        return None

    @staticmethod
    def _find_table_html(page) -> Optional[str]:
        # Thử vài dạng cấu trúc kết quả đã biết của PPStructureV3.
        candidates = []
        if isinstance(page, dict):
            candidates.append(page)
        else:
            as_dict = getattr(page, "json", None) or getattr(page, "res", None)
            if isinstance(as_dict, dict):
                candidates.append(as_dict)

        for c in candidates:
            table_list = c.get("table_res_list") or c.get("table_result") or []
            for t in table_list:
                html = t.get("pred_html") or t.get("html")
                if html:
                    return html
        return None


def create_engine(name: str) -> BaseOCREngine:
    if name == "tesseract":
        return TesseractEngine()
    if name == "paddleocr":
        return PaddleOCREngine()
    raise ValueError(f"OCR engine không hợp lệ: {name}")
