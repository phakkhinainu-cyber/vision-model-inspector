"""ตัวติดตามรถแบบ ByteTrack (ย่อ) — จับคู่กล่องที่ความมั่นใจสูงก่อน แล้วจึงใช้กล่องความมั่นใจต่ำช่วยต่อ track

ไม่ต้องใช้ไลบรารีเพิ่ม (numpy อย่างเดียว) และใช้เวลาจริงในการตัดสินว่ารถหายจากภาพ
เพราะเมื่อไม่มีความเคลื่อนไหว โปรแกรมจะหยุดรันโมเดลเพื่อประหยัด CPU
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .yolo import Detection


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-6)


def greedy_match(cost_iou: np.ndarray, thresh: float) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    matches: list[tuple[int, int]] = []
    used_r: set[int] = set()
    used_c: set[int] = set()
    if cost_iou.size:
        order = np.dstack(np.unravel_index(np.argsort(-cost_iou, axis=None), cost_iou.shape))[0]
        for r, c in order:
            if cost_iou[r, c] < thresh:
                break
            if r in used_r or c in used_c:
                continue
            matches.append((int(r), int(c)))
            used_r.add(int(r))
            used_c.add(int(c))
    rows = set(range(cost_iou.shape[0])) - used_r
    cols = set(range(cost_iou.shape[1])) - used_c
    return matches, rows, cols


@dataclass
class Track:
    id: int
    box: np.ndarray
    score: float
    first_ts: float
    last_ts: float
    hits: int = 1
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    classes: Counter = field(default_factory=Counter)
    centers: list[tuple[float, float, float]] = field(default_factory=list)  # (ts, cx, cy)
    updated: bool = True
    data: dict[str, Any] = field(default_factory=dict)  # ข้อมูลของ pipeline (ผลโหวต ภาพ ฯลฯ)

    @property
    def confirmed(self) -> bool:
        return self.hits >= 2

    @property
    def cls(self) -> int:
        return self.classes.most_common(1)[0][0] if self.classes else -1

    @property
    def center(self) -> tuple[float, float]:
        b = self.box
        return float((b[0] + b[2]) / 2), float((b[1] + b[3]) / 2)

    def predict(self, dt_frames: float = 1.0) -> np.ndarray:
        return self.box + self.velocity * dt_frames


class ByteTracker:
    def __init__(self, high: float = 0.45, low: float = 0.15, match_iou: float = 0.25,
                 timeout_s: float = 2.5) -> None:
        self.high, self.low, self.match_iou, self.timeout_s = high, low, match_iou, timeout_s
        self.tracks: list[Track] = []
        self._next = 1

    def update(self, dets: list[Detection], ts: float) -> tuple[list[Track], list[Track]]:
        """คืน (track ที่ยังอยู่, track ที่จบแล้วในรอบนี้)"""
        for t in self.tracks:
            t.updated = False
        boxes = np.array([d.box for d in dets], dtype=np.float32).reshape(-1, 4)
        scores = np.array([d.score for d in dets], dtype=np.float32)
        hi = np.where(scores >= self.high)[0]
        lo = np.where((scores >= self.low) & (scores < self.high))[0]
        preds = np.array([t.predict() for t in self.tracks], dtype=np.float32).reshape(-1, 4)
        # รอบที่ 1: กล่องความมั่นใจสูง กับทุก track
        m1, rem_t, rem_hi = greedy_match(iou_matrix(preds, boxes[hi]), self.match_iou)
        for ti, di in m1:
            self._apply(self.tracks[ti], dets[hi[di]], ts)
        # รอบที่ 2: กล่องความมั่นใจต่ำ กับ track ที่เหลือ
        rem_t_list = sorted(rem_t)
        m2, _, _ = greedy_match(iou_matrix(preds[rem_t_list], boxes[lo]), self.match_iou)
        for ti, di in m2:
            self._apply(self.tracks[rem_t_list[ti]], dets[lo[di]], ts)
        # กล่องสูงที่เหลือ = รถคันใหม่
        for di in sorted(rem_hi):
            d = dets[hi[di]]
            t = Track(self._next, d.box.copy(), d.score, ts, ts)
            t.classes[d.cls] += 1
            t.centers.append((ts, *t.center))
            self._next += 1
            self.tracks.append(t)
        ended = [t for t in self.tracks if ts - t.last_ts > self.timeout_s]
        self.tracks = [t for t in self.tracks if ts - t.last_ts <= self.timeout_s]
        return self.tracks, ended

    def flush(self) -> list[Track]:
        ended, self.tracks = self.tracks, []
        return ended

    def expire(self, ts: float) -> list[Track]:
        ended = [t for t in self.tracks if ts - t.last_ts > self.timeout_s]
        self.tracks = [t for t in self.tracks if ts - t.last_ts <= self.timeout_s]
        return ended

    @staticmethod
    def _apply(t: Track, d: Detection, ts: float) -> None:
        nb = d.box
        t.velocity = 0.6 * t.velocity + 0.4 * (nb - t.box)
        t.box = nb.copy()
        t.score = d.score
        t.last_ts = ts
        t.hits += 1
        t.updated = True
        t.classes[d.cls] += 1
        t.centers.append((ts, *t.center))
        if len(t.centers) > 300:
            del t.centers[: len(t.centers) - 300]
