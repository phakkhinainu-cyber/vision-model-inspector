"""โซน ROI และเส้นเสมือน (พิกัดแบบสัดส่วน 0..1 ของภาพ)"""
from __future__ import annotations

import json
from typing import Sequence

import cv2
import numpy as np

Point = tuple[float, float]


def parse_points(s: str | Sequence | None) -> list[Point]:
    if not s:
        return []
    pts = json.loads(s) if isinstance(s, str) else s
    out = []
    for p in pts:
        x, y = float(p[0]), float(p[1])
        out.append((min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)))
    return out


def roi_mask(poly: list[Point], w: int, h: int) -> np.ndarray | None:
    if len(poly) < 3:
        return None
    m = np.zeros((h, w), dtype=np.uint8)
    pts = np.array([[x * w, y * h] for x, y in poly], dtype=np.int32)
    cv2.fillPoly(m, [pts], 255)
    return m


def point_in_poly(poly: list[Point], x: float, y: float) -> bool:
    """x, y เป็นสัดส่วน 0..1"""
    if len(poly) < 3:
        return True
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def side_of_line(line: list[Point], x: float, y: float) -> float:
    (ax, ay), (bx, by) = line
    return (bx - ax) * (y - ay) - (by - ay) * (x - ax)


def crossing(line: list[Point], p0: Point, p1: Point) -> int:
    """คืน +1 ถ้าข้ามจากด้านลบไปด้านบวก, -1 ถ้าข้ามกลับ, 0 ถ้าไม่ข้าม (ต้องข้ามภายในช่วงของเส้น)"""
    if len(line) != 2:
        return 0
    s0 = side_of_line(line, *p0)
    s1 = side_of_line(line, *p1)
    if s0 == 0 or s1 == 0 or (s0 > 0) == (s1 > 0):
        return 0
    # จุดตัดต้องอยู่บนช่วงของเส้น (เผื่อ 10%)
    (ax, ay), (bx, by) = line
    dx, dy = bx - ax, by - ay
    t_num = (p0[0] - ax) * (p1[1] - p0[1]) - (p0[1] - ay) * (p1[0] - p0[0])
    t_den = dx * (p1[1] - p0[1]) - dy * (p1[0] - p0[0])
    if abs(t_den) < 1e-12:
        return 0
    t = t_num / t_den
    if t < -0.1 or t > 1.1:
        return 0
    return 1 if s1 > 0 else -1


def net_side_motion(line: list[Point], start: Point, end: Point) -> int:
    """ใช้เมื่อรถไม่ได้ข้ามเส้น: ทิศการเคลื่อนที่เทียบกับแนวตั้งฉากของเส้น (+1/-1/0)"""
    if len(line) == 2:
        d = side_of_line(line, *end) - side_of_line(line, *start)
    else:
        d = end[1] - start[1]  # ไม่มีเส้น: เลื่อนลง = บวก
    if abs(d) < 1e-4:
        return 0
    return 1 if d > 0 else -1
