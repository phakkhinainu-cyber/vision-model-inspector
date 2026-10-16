"""อ่านป้ายจากภาพครอป: ปรับภาพ -> แยกบรรทัด -> OCR -> แยกวิเคราะห์ป้ายไทย -> สีป้าย"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from ..plates.colors import plate_colors
from ..plates.parser import ParsedPlate, format_display, normalize_plate_text, parse_plate
from .ocr.base import OcrEngine
from .ocr.textdet import DbTextDetector, projection_lines
from .preprocess import prepare_plate, sharpness


@dataclass
class PlateRead:
    parsed: ParsedPlate
    bg: str
    fg: str
    ir: bool
    n_lines: int
    sharpness: float
    processed: np.ndarray


class PlateReader:
    def __init__(self, ocr: OcrEngine, textdet: DbTextDetector | None = None,
                 min_province_score: float = 80.0) -> None:
        self.ocr = ocr
        self.textdet = textdet
        self.min_province_score = min_province_score

    def _ocr(self, img: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> tuple[ParsedPlate, int]:
        crops = [img[y1:y2, x1:x2] for x1, y1, x2, y2 in boxes[:4] if y2 - y1 > 4 and x2 - x1 > 4]
        texts = self.ocr.recognize(crops) if crops else []
        parsed = parse_plate(texts, self.min_province_score)
        if not parsed.valid and len(texts) > 2:
            parsed = _try_pairs(texts, parsed, self.min_province_score)
        return parsed, len(crops)

    def read(self, plate_crop: np.ndarray, night: bool = False, ir_frame: bool = False) -> PlateRead:
        bg, fg, achromatic = plate_colors(plate_crop)
        if ir_frame:
            bg, fg = "unknown", "unknown"
        img = prepare_plate(plate_crop, night=night or ir_frame)
        # แยกบรรทัดแบบ projection ก่อน (เร็ว) ถ้าผลไม่ครบจึงใช้โมเดลตรวจจับข้อความ
        parsed, n = self._ocr(img, projection_lines(img))
        if self.textdet is not None and (not parsed.valid or parsed.province is None):
            try:
                p2, n2 = self._ocr(img, self.textdet.detect(img))
                if (p2.valid, p2.province is not None, p2.confidence) > (parsed.valid, parsed.province is not None,
                                                                          parsed.confidence):
                    parsed, n = p2, n2
            except Exception:  # noqa: BLE001
                pass
        return PlateRead(parsed, bg, fg, ir_frame, n, sharpness(plate_crop), img)


def _try_pairs(texts: list[tuple[str, float]], cur: ParsedPlate, min_score: float) -> ParsedPlate:
    """มีบรรทัดขยะ (เช่นตัวหนังสือบนกรอบป้าย): ลองจับคู่บรรทัดอื่นๆ"""
    for i, j in combinations(range(len(texts)), 2):
        cand = [texts[i], texts[j]]
        rest = [t for k, t in enumerate(texts) if k not in (i, j)]
        n, _, ok = normalize_plate_text(cand[0][0] + cand[1][0])
        if ok:
            p = parse_plate(cand + rest, min_score)
            if p.valid:
                return p
            p.norm, p.valid, p.kind = n, True, "car"
            p.display = format_display(n)
            return p
    return cur
