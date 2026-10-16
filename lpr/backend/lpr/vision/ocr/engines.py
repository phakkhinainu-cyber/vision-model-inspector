"""OCR engine ทางเลือก (ติดตั้งเพิ่มเมื่อรันจากซอร์ส) และตัวเลือก engine อัตโนมัติ"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .base import NullEngine, OcrEngine

log = logging.getLogger(__name__)


class PaddleEngine:
    """PaddleOCR 3.x (paddlepaddle) โมเดล th_PP-OCRv5_mobile_rec"""

    name = "PaddleOCR th_PP-OCRv5_mobile_rec"

    def __init__(self, model_name: str = "th_PP-OCRv5_mobile_rec", device: str = "auto") -> None:
        from paddleocr import TextRecognition  # type: ignore[import-not-found]

        kw = {"device": "gpu"} if device == "cuda" else ({"device": "cpu"} if device == "cpu" else {})
        self.rec = TextRecognition(model_name=model_name, **kw)

    def recognize(self, line_images: list[np.ndarray]) -> list[tuple[str, float]]:
        if not line_images:
            return []
        res = self.rec.predict(line_images)
        return [(r.get("rec_text", ""), float(r.get("rec_score", 0.0))) for r in res]


class EasyOcrEngine:
    """EasyOCR ภาษาไทย+อังกฤษ (ตัวสำรอง)"""

    name = "EasyOCR (th,en)"

    def __init__(self, device: str = "auto") -> None:
        import easyocr  # type: ignore[import-not-found]

        gpu = device in ("auto", "cuda")
        try:
            import torch  # type: ignore[import-not-found]

            gpu = gpu and torch.cuda.is_available()
        except Exception:  # noqa: BLE001
            gpu = False
        self.reader = easyocr.Reader(["th", "en"], gpu=gpu, verbose=False)

    def recognize(self, line_images: list[np.ndarray]) -> list[tuple[str, float]]:
        out = []
        for img in line_images:
            h, w = img.shape[:2]
            r = self.reader.recognize(img, horizontal_list=[[0, w, 0, h]], free_list=[], detail=1)
            if r:
                out.append((" ".join(x[1] for x in r), float(np.mean([x[2] for x in r]))))
            else:
                out.append(("", 0.0))
        return out


def create_engine(choice: str, rec_model: Path | None, rec_dict: Path | None, device: str = "auto",
                  threads: int = 0) -> OcrEngine:
    order = {"auto": ["onnx", "paddle", "easyocr"], "onnx": ["onnx", "paddle", "easyocr"],
             "paddle": ["paddle", "onnx", "easyocr"], "easyocr": ["easyocr", "onnx", "paddle"]}.get(choice, ["onnx"])
    for name in order:
        try:
            if name == "onnx" and rec_model and rec_dict:
                from .onnx_ppocr import OnnxPPOCR

                return OnnxPPOCR(rec_model, rec_dict, device, threads)
            if name == "paddle":
                return PaddleEngine(device=device)
            if name == "easyocr":
                return EasyOcrEngine(device=device)
        except Exception as e:  # noqa: BLE001
            log.info("OCR engine %s ใช้ไม่ได้: %s", name, e)
    log.error("ไม่มี OCR engine ที่ใช้ได้ — ทุกเหตุการณ์จะเป็น อ่านไม่ได้")
    return NullEngine()
