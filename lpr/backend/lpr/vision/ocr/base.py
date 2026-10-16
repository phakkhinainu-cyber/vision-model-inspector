"""interface ของ OCR engine — เปลี่ยน engine ได้ (ONNX PP-OCRv5, PaddleOCR, EasyOCR, โมเดลที่ fine-tune เอง,
หรือบริการเชิงพาณิชย์ในอนาคต) โดยทำคลาสใหม่ที่มีเมธอด recognize()"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class OcrEngine(Protocol):
    name: str

    def recognize(self, line_images: list[np.ndarray]) -> list[tuple[str, float]]:
        """รับภาพบรรทัดข้อความ (BGR) คืน [(ข้อความ, ความมั่นใจ 0-1)] ตามลำดับเดียวกัน"""
        ...


class NullEngine:
    name = "none"

    def recognize(self, line_images: list[np.ndarray]) -> list[tuple[str, float]]:
        return [("", 0.0) for _ in line_images]
