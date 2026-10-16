"""วิเคราะห์สีป้ายทะเบียน (สีพื้นและสีตัวอักษร) จากค่า HSV

พื้นขาวอักษรดำ = รถยนต์ส่วนบุคคล, อักษรเขียว = กระบะ/บรรทุกส่วนบุคคล, อักษรน้ำเงิน = รถตู้/นั่งเกิน 7 คน,
พื้นเหลือง = รับจ้าง/แท็กซี่/สาธารณะ, ป้ายแดง = รถใหม่ยังไม่จดทะเบียน
ภาพกลางคืนจาก IR เป็นขาวดำ จะบอกสีไม่ได้ (unknown)
"""
from __future__ import annotations

import cv2
import numpy as np


def _hue_name(h: float, s: float, v: float) -> str:
    # OpenCV: H 0-179, S/V 0-255
    if v < 70:
        return "black"
    if s < 55:
        return "white" if v > 110 else ("black" if v < 90 else "unknown")
    if h < 8 or h >= 168:
        return "red"
    if h < 18:
        return "orange"
    if h < 38:
        return "yellow"
    if h < 88:
        return "green"
    if h < 135:
        return "blue"
    return "red"


def plate_colors(plate_bgr: np.ndarray) -> tuple[str, str, bool]:
    """คืน (สีพื้น, สีตัวอักษร, เป็นภาพ IR/ขาวดำหรือไม่)"""
    if plate_bgr is None or plate_bgr.size == 0:
        return "unknown", "unknown", False
    img = plate_bgr
    h, w = img.shape[:2]
    # ตัดขอบ 8% เพื่อไม่ให้กรอบป้าย/ตัวรถปน
    y0, y1, x0, x1 = int(h * 0.08), int(h * 0.92), int(w * 0.06), int(w * 0.94)
    img = img[y0:y1, x0:x1]
    if img.size == 0:
        return "unknown", "unknown", False
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    b, g, r = [c.astype(np.int16) for c in cv2.split(img)]
    chroma = np.maximum(np.maximum(np.abs(b - g), np.abs(g - r)), np.abs(b - r))
    is_gray = float(np.mean(chroma)) < 6.0 and float(np.percentile(chroma, 95)) < 16
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    light = th > 0
    # พื้นป้ายคือส่วนที่มีพื้นที่มากกว่า
    bg_mask = light if light.mean() >= 0.5 else ~light
    fg_mask = ~bg_mask
    if is_gray:
        # ป้ายขาวอักษรดำเป็นสีเทาอยู่แล้ว (ภาพ IR ทั้งเฟรมให้ผู้เรียกตัดสินจากทั้งภาพ)
        bgv = float(np.median(gray[bg_mask])) if bg_mask.any() else 0.0
        return ("white" if bgv > 90 else "unknown"), "black", True

    def med(mask: np.ndarray, darkest: bool = False) -> tuple[float, float, float]:
        if mask.sum() < 10:
            return 0.0, 0.0, 0.0
        px = hsv[mask]
        if darkest:  # ขอบตัวอักษรเบลอปนสีพื้น ใช้เฉพาะครึ่งที่เข้มที่สุด
            px = px[px[:, 2] <= np.percentile(px[:, 2], 50)]
        # hue เป็นวงกลม ใช้ค่าเฉลี่ยแบบเวกเตอร์
        ang = px[:, 0].astype(np.float32) * (np.pi / 90.0)
        hue = (np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) / 2.0) % 180
        return float(hue), float(np.median(px[:, 1])), float(np.median(px[:, 2]))

    bg = _hue_name(*med(bg_mask))
    fg = _hue_name(*med(fg_mask, darkest=True))
    if bg == "orange":
        bg = "yellow"
    if bg == "red":
        fg = "black"
    return bg, fg, False


def plate_color_code(bg: str, fg: str) -> str:
    return f"{bg}/{fg}"
