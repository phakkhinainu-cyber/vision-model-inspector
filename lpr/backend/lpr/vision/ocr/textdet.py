"""แยกบรรทัดข้อความในภาพป้าย

1. ใช้โมเดลตรวจจับข้อความ PP-OCRv5_mobile_det (DBNet, ONNX) ถ้ามี
2. ไม่เช่นนั้นใช้ projection profile ตามแนวนอน (ป้ายรถยนต์ 2 บรรทัด, ป้ายจักรยานยนต์ 3 บรรทัด)
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..runtime import make_session

Box = tuple[int, int, int, int]


class DbTextDetector:
    def __init__(self, model_path: Path, device: str = "auto", threads: int = 0) -> None:
        self.sess = make_session(model_path, device, threads)
        self.input_name = self.sess.get_inputs()[0].name
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def detect(self, img: np.ndarray, side: int = 480, thresh: float = 0.3, box_thresh: float = 0.55,
               unclip: float = 1.6) -> list[Box]:
        h, w = img.shape[:2]
        s = side / max(h, w)
        nh, nw = max(32, int(round(h * s / 32)) * 32), max(32, int(round(w * s / 32)) * 32)
        x = cv2.resize(img, (nw, nh)).astype(np.float32) / 255.0
        x = ((x - self.mean) / self.std).transpose(2, 0, 1)[None]
        pred = self.sess.run(None, {self.input_name: x})[0][0, 0]
        bitmap = (pred > thresh).astype(np.uint8)
        cnts, _ = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes: list[Box] = []
        sx, sy = w / nw, h / nh
        for c in cnts:
            if len(c) < 4:
                continue
            rect = cv2.minAreaRect(c)
            (cx, cy), (rw, rh), ang = rect
            if min(rw, rh) < 3:
                continue
            mask = np.zeros_like(bitmap)
            cv2.drawContours(mask, [c], -1, 1, -1)
            score = float(pred[mask > 0].mean()) if mask.any() else 0.0
            if score < box_thresh:
                continue
            area, peri = rw * rh, 2 * (rw + rh)
            d = area * unclip / max(peri, 1e-6)
            rect = ((cx, cy), (rw + 2 * d, rh + 2 * d), ang)
            pts = cv2.boxPoints(rect)
            x1, y1 = pts.min(0)
            x2, y2 = pts.max(0)
            boxes.append((int(max(0, x1 * sx)), int(max(0, y1 * sy)), int(min(w, x2 * sx)), int(min(h, y2 * sy))))
        return merge_rows(boxes, h)


def merge_rows(boxes: list[Box], img_h: int) -> list[Box]:
    """รวมกล่องคำที่อยู่บรรทัดเดียวกัน (เช่น "1กข" กับ "4521") เป็นกล่องบรรทัดเดียว"""
    boxes = sorted(boxes, key=lambda b: (b[1] + b[3]) / 2)
    rows: list[list[int]] = []
    for b in boxes:
        placed = False
        for r in rows:
            ov = min(r[3], b[3]) - max(r[1], b[1])
            if ov > 0.5 * min(r[3] - r[1], b[3] - b[1]):
                r[0], r[1], r[2], r[3] = min(r[0], b[0]), min(r[1], b[1]), max(r[2], b[2]), max(r[3], b[3])
                placed = True
                break
        if not placed:
            rows.append(list(b))
    out = [tuple(r) for r in rows if (r[3] - r[1]) >= 0.08 * img_h and (r[2] - r[0]) >= 8]
    return sorted(out, key=lambda b: b[1])  # type: ignore[return-value]


def projection_lines(img: np.ndarray) -> list[Box]:
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if th.mean() > 127:  # ตัวอักษรสว่างบนพื้นเข้ม
        th = 255 - th
    # ตัดขอบป้าย
    bx, by = int(w * 0.03), int(h * 0.05)
    th[:by], th[-by:], th[:, :bx], th[:, -bx:] = 0, 0, 0, 0
    prof = th.sum(1).astype(np.float32)
    k = max(3, h // 25)
    prof = np.convolve(prof, np.ones(k) / k, mode="same")
    ar = w / max(h, 1)
    splits_expect = [0.62] if ar >= 1.7 else [0.37, 0.64]
    cuts = [0]
    for e in splits_expect:
        lo, hi = int(h * (e - 0.15)), int(h * (e + 0.13))
        lo = max(lo, cuts[-1] + int(h * 0.15))
        if hi <= lo:
            continue
        cuts.append(lo + int(np.argmin(prof[lo:hi])))
    cuts.append(h)
    boxes: list[Box] = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        seg = th[a:b]
        cols = np.where(seg.sum(0) > 255 * 2)[0]
        rows = np.where(seg.sum(1) > 255 * 2)[0]
        if len(cols) < 4 or len(rows) < 3:
            continue
        pad = max(2, (b - a) // 10)
        boxes.append((max(0, cols[0] - pad), max(0, a + rows[0] - pad), min(w, cols[-1] + pad),
                      min(h, a + rows[-1] + pad)))
    return boxes
