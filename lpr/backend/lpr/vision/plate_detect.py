"""หาป้ายทะเบียนในกรอบรถ: ใช้โมเดล YOLO ป้าย (ถ้ามี) ไม่เช่นนั้นใช้วิธีประมวลผลภาพแบบดั้งเดิม"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .yolo import YoloDetector


@dataclass
class PlateBox:
    x1: int
    y1: int
    x2: int
    y2: int
    score: float

    def crop(self, img: np.ndarray, margin: float = 0.06) -> np.ndarray:
        h, w = img.shape[:2]
        mx = int((self.x2 - self.x1) * margin)
        my = int((self.y2 - self.y1) * margin * 1.5)
        return img[max(0, self.y1 - my):min(h, self.y2 + my), max(0, self.x1 - mx):min(w, self.x2 + mx)].copy()


class PlateDetector:
    def __init__(self, model_path: Path | None, device: str = "auto", threads: int = 0) -> None:
        self.model = YoloDetector(model_path, device, threads) if model_path else None
        self.kind = "yolo" if self.model else "classic"

    def detect(self, vehicle_crop: np.ndarray, conf: float = 0.3) -> PlateBox | None:
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None
        if self.model is not None:
            dets = self.model.detect(vehicle_crop, conf=conf, max_det=5)
            if dets:
                h = vehicle_crop.shape[0]
                # เลือกป้ายที่มั่นใจสูง และอยู่ค่อนไปทางล่างของรถเล็กน้อย
                d = max(dets, key=lambda d: d.score + 0.1 * ((d.y1 + d.y2) / 2 / h))
                return PlateBox(int(d.x1), int(d.y1), int(d.x2), int(d.y2), d.score)
            return None
        return classic_find_plate(vehicle_crop)


def classic_find_plate(img: np.ndarray) -> PlateBox | None:
    """หาบริเวณสี่เหลี่ยมที่มีขอบตัวอักษรหนาแน่นและสัดส่วนเหมือนป้าย (รถยนต์ ~2.3:1, จักรยานยนต์ ~1.4:1)"""
    h, w = img.shape[:2]
    if h < 40 or w < 40:
        return None
    y_off = int(h * 0.3)
    roi = img[y_off:]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    k = max(3, int(w / 60)) | 1
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (k * 3, k)))
    gx = cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=3)
    gx = np.abs(gx)
    gx = (255 * (gx - gx.min()) / (gx.max() - gx.min() + 1e-6)).astype(np.uint8)
    gx = cv2.GaussianBlur(gx, (5, 5), 0)
    closed = cv2.morphologyEx(gx, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k * 3, k)))
    _, th = cv2.threshold(closed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.erode(th, None, iterations=1)
    th = cv2.dilate(th, None, iterations=2)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 0.0
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w * 0.12 or bw > w * 0.7 or bh < 10:
            continue
        ar = bw / bh
        if not (1.2 <= ar <= 5.0):
            continue
        patch = gray[y:y + bh, x:x + bw]
        bright = float(np.percentile(patch, 75))
        density = float((th[y:y + bh, x:x + bw] > 0).mean())
        center_bonus = 1.0 - abs((x + bw / 2) / w - 0.5)
        ar_bonus = 1.0 - min(abs(ar - 2.3), abs(ar - 1.4)) / 3
        score = density * (bright / 255) * center_bonus * max(ar_bonus, 0.1)
        if score > best_score:
            best, best_score = (x, y, bw, bh), score
    if best is None or best_score < 0.08:
        return None
    x, y, bw, bh = best
    return PlateBox(x, y + y_off, x + bw, y + y_off + bh, min(0.99, best_score))
