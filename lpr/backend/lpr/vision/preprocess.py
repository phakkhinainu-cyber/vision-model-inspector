"""ปรับภาพป้ายก่อน OCR: แก้มุมเอียง/มุมมอง, ขยาย, CLAHE, เพิ่มความคม"""
from __future__ import annotations

import cv2
import numpy as np


def sharpness(img: np.ndarray) -> float:
    """ความคมของภาพ (variance of Laplacian) ใช้เลือกเฟรมที่ดีที่สุด"""
    if img is None or img.size == 0:
        return 0.0
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if g.shape[0] > 120:
        g = cv2.resize(g, (int(g.shape[1] * 120 / g.shape[0]), 120), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def _order_quad(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(1)
    d = np.diff(pts, axis=1).reshape(-1)
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype=np.float32)


def find_plate_quad(img: np.ndarray) -> np.ndarray | None:
    """หาขอบป้าย 4 มุม (สำหรับแก้มุมมอง) ถ้าหาไม่ได้คืน None"""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 40, 40)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best, best_area = None, 0.0
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 0.35 * w * h or area > 0.98 * w * h:
            continue
        approx = cv2.approxPolyDP(c, 0.03 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx) and area > best_area:
            best, best_area = approx, area
    return _order_quad(best) if best is not None else None


def deskew(img: np.ndarray) -> np.ndarray:
    quad = find_plate_quad(img)
    if quad is not None:
        tl, tr, br, bl = quad
        wd = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
        ht = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
        if wd > 20 and ht > 10:
            dst = np.array([[0, 0], [wd - 1, 0], [wd - 1, ht - 1], [0, ht - 1]], dtype=np.float32)
            m = cv2.getPerspectiveTransform(quad, dst)
            return cv2.warpPerspective(img, m, (wd, ht), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    # ไม่พบขอบ: ประมาณมุมเอียงจากพื้นป้ายสีสว่าง
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(th)
    if n <= 1:
        return img
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < 0.25 * gray.size:
        return img
    ys, xs = np.where(labels == i)
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    if rw < rh:
        ang += 90
    ang = ((ang + 45) % 90) - 45
    if 1.0 < abs(ang) < 25:
        m = cv2.getRotationMatrix2D((img.shape[1] / 2, img.shape[0] / 2), ang, 1.0)
        return cv2.warpAffine(img, m, (img.shape[1], img.shape[0]), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return img


def enhance(img: np.ndarray, night: bool = False, target_h: int = 128) -> np.ndarray:
    h, w = img.shape[:2]
    if h < target_h:
        s = target_h / h
        img = cv2.resize(img, (int(w * s), target_h), interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=3.0 if night else 2.0, tileGridSize=(4, 8))
    lab[..., 0] = clahe.apply(lab[..., 0])
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if night:
        img = cv2.fastNlMeansDenoisingColored(img, None, 5, 5, 7, 15)
    blur = cv2.GaussianBlur(img, (0, 0), 1.2)
    return cv2.addWeighted(img, 1.6, blur, -0.6, 0)


def prepare_plate(crop: np.ndarray, night: bool = False) -> np.ndarray:
    return enhance(deskew(crop), night=night)
