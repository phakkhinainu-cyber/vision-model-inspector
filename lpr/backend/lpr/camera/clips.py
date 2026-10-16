"""ring buffer ของภาพย้อนหลัง และการเขียนคลิปสั้น (3 วินาทีก่อน – 5 วินาทีหลังเหตุการณ์)

คลิปเป็น WebM (VP8) ซึ่งเล่นได้ในเบราว์เซอร์ทุกตัวและ OpenCV เขียนได้เองโดยไม่ต้องติดตั้งเพิ่ม
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


class RingBuffer:
    def __init__(self, seconds: float, fps: int = 10, max_width: int = 1280) -> None:
        self.seconds = seconds
        self.fps = fps
        self.max_width = max_width
        self._buf: deque[tuple[float, bytes]] = deque()
        self._lock = threading.Lock()
        self._last = 0.0

    def push(self, frame: np.ndarray, ts: float) -> None:
        if ts - self._last < 1.0 / self.fps:
            return
        self._last = ts
        h, w = frame.shape[:2]
        if w > self.max_width:
            frame = cv2.resize(frame, (self.max_width, int(h * self.max_width / w)), interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return
        with self._lock:
            self._buf.append((ts, jpg.tobytes()))
            while self._buf and ts - self._buf[0][0] > self.seconds:
                self._buf.popleft()

    def window(self, t0: float, t1: float) -> list[tuple[float, bytes]]:
        with self._lock:
            return [(t, b) for t, b in self._buf if t0 <= t <= t1]


def write_clip(frames: list[tuple[float, bytes]], path: Path, fps: int) -> bool:
    if len(frames) < 2:
        return False
    first = cv2.imdecode(np.frombuffer(frames[0][1], np.uint8), cv2.IMREAD_COLOR)
    h, w = first.shape[:2]
    w2, h2 = w - (w % 2), h - (h % 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"VP80"), fps, (w2, h2))
    if not vw.isOpened():
        log.warning("เขียนคลิป WebM ไม่ได้")
        return False
    for _, b in frames:
        img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        if img.shape[:2] != (h2, w2):
            img = cv2.resize(img, (w2, h2))
        vw.write(img)
    vw.release()
    return path.exists() and path.stat().st_size > 0


class ClipScheduler:
    """รอจนครบเวลาหลังเหตุการณ์ แล้วเขียนคลิปใน thread แยก"""

    def __init__(self, ring: RingBuffer, out_dir: Path, pre: float, post: float, fps: int,
                 on_done) -> None:  # type: ignore[no-untyped-def]
        self.ring, self.out_dir, self.pre, self.post, self.fps = ring, out_dir, pre, post, fps
        self.on_done = on_done
        self._pending: list[tuple[float, float, str]] = []
        self._lock = threading.Lock()

    def request(self, uid: str, event_ts: float) -> None:
        with self._lock:
            self._pending.append((event_ts + self.post, event_ts, uid))

    def tick(self) -> None:
        now = time.time()
        due = []
        with self._lock:
            keep = []
            for item in self._pending:
                (due if item[0] <= now else keep).append(item)
            self._pending = keep
        for _, ts, uid in due:
            frames = self.ring.window(ts - self.pre, ts + self.post)
            path = self.out_dir / f"{uid}.webm"
            threading.Thread(target=self._write, args=(frames, path, uid), daemon=True).start()

    def _write(self, frames: list[tuple[float, bytes]], path: Path, uid: str) -> None:
        try:
            if write_clip(frames, path, self.fps):
                self.on_done(uid, str(path))
        except Exception:  # noqa: BLE001
            log.exception("write clip failed")
