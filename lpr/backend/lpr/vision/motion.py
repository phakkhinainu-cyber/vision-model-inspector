"""ตรวจความเคลื่อนไหวในโซน ROI และตรวจกลางวัน/กลางคืน (ประหยัด CPU: ไม่มีความเคลื่อนไหว = ไม่รันโมเดล)"""
from __future__ import annotations

import cv2
import numpy as np

from .geometry import Point, roi_mask


class MotionDetector:
    def __init__(self, roi: list[Point], threshold: float = 0.004, width: int = 320) -> None:
        self.roi = roi
        self.threshold = threshold
        self.width = width
        self._bg: np.ndarray | None = None
        self._mask: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None
        self.last_ratio = 0.0

    def update(self, frame_bgr: np.ndarray) -> bool:
        h, w = frame_bgr.shape[:2]
        sh = int(round(h * self.width / w))
        small = cv2.resize(frame_bgr, (self.width, sh), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
        if self._shape != gray.shape:
            self._shape = gray.shape
            self._bg = gray.copy()
            self._mask = roi_mask(self.roi, self.width, sh)
            return False
        assert self._bg is not None
        diff = cv2.absdiff(gray, self._bg)
        cv2.accumulateWeighted(gray, self._bg, 0.05)
        moving = diff > 22
        if self._mask is not None:
            moving &= self._mask > 0
            area = max(1, int((self._mask > 0).sum()))
        else:
            area = moving.size
        self.last_ratio = float(moving.sum()) / area
        return self.last_ratio >= self.threshold


class DayNight:
    """สลับโหมดกลางวัน/กลางคืนตามความสว่าง และภาพขาวดำจาก IR (มี hysteresis กันสลับไปมา)"""

    def __init__(self, night_brightness: int = 70, hold_s: float = 20.0) -> None:
        self.night_brightness = night_brightness
        self.hold_s = hold_s
        self.night = False
        self._since: float | None = None
        self.brightness = 0.0
        self.ir = False

    def update(self, frame_bgr: np.ndarray, ts: float) -> bool:
        small = cv2.resize(frame_bgr, (160, 90), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        self.brightness = float(hsv[..., 2].mean())
        self.ir = float(hsv[..., 1].mean()) < 10
        want = self.brightness < self.night_brightness or self.ir
        if not hasattr(self, "_init"):
            self._init = True
            self.night = want
            return self.night
        if want == self.night:
            self._since = None
        elif self._since is None:
            self._since = ts
        elif ts - self._since >= self.hold_s:
            self.night = want
            self._since = None
        return self.night
