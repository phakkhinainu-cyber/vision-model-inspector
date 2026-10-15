"""Inference thread with a latest-frame slot (bounded, size 1).

* Capture never blocks on inference: a new frame replaces an unprocessed one
  (counted as dropped), so memory use is bounded and latency stays low.
* Every result carries the FramePacket it was computed on — the UI draws boxes
  only on that exact frame, never on a newer frame.
* Snapshot jobs have priority and run on the frame copy stored in the snapshot.
* ``pause()`` stops live inference (used while Grad-CAM runs); preview frames
  still flow.
"""
from __future__ import annotations

import collections
import logging
import threading
import time

from ..core.types import DetectionResult, FramePacket, InferenceSettings
from ..sources.base import FpsMeter

log = logging.getLogger(__name__)


class LatestFrameSlot:
    def __init__(self):
        self._pkt = None
        self.dropped = 0
        self.received = 0
        self._lock = threading.Lock()

    def put(self, pkt: FramePacket):
        with self._lock:
            if self._pkt is not None:
                self.dropped += 1
            self._pkt = pkt
            self.received += 1

    def take(self):
        with self._lock:
            p, self._pkt = self._pkt, None
            return p

    def peek_pending(self) -> bool:
        with self._lock:
            return self._pkt is not None

    def clear(self):
        with self._lock:
            self._pkt = None

    def __len__(self):
        with self._lock:
            return 0 if self._pkt is None else 1


class InferenceWorker(threading.Thread):
    def __init__(self, on_result=None, on_error=None):
        super().__init__(daemon=True, name="inference")
        self.on_result = on_result          # (FramePacket, DetectionResult, kind, tag)
        self.on_error = on_error            # (str)
        self.slot = LatestFrameSlot()
        self._jobs = collections.deque(maxlen=16)
        self._cv = threading.Condition()
        self._busy = threading.Lock()
        self._stop = False
        self._paused = False
        self.pause_reason = ""
        self._adapter = None
        self._settings = InferenceSettings()
        self.every_n = 1
        self.max_fps = 0.0
        self._since_last = 0
        self._last_t = 0.0
        self.infer_fps = FpsMeter()
        self.last_ms = 0.0
        self.live_enabled = True

    # ------------------------------------------------------------ config
    def set_adapter(self, adapter):
        """Swap model safely: waits for a running inference to finish."""
        with self._busy:
            self._adapter = adapter
            self.slot.clear()
            self._jobs.clear()
        self.infer_fps.reset()

    @property
    def adapter(self):
        return self._adapter

    def set_settings(self, s: InferenceSettings):
        with self._cv:
            self._settings = s.copy()

    def settings(self) -> InferenceSettings:
        with self._cv:
            return self._settings.copy()

    def set_rate(self, every_n: int, max_fps: float):
        self.every_n = max(1, int(every_n))
        self.max_fps = max(0.0, float(max_fps))

    def pause(self, reason: str = ""):
        with self._cv:
            self._paused = True
            self.pause_reason = reason
        self.slot.clear()

    def resume(self):
        with self._cv:
            self._paused = False
            self.pause_reason = ""
            self._cv.notify_all()

    @property
    def paused(self) -> bool:
        return self._paused

    # ------------------------------------------------------------ input
    def submit_frame(self, pkt: FramePacket):
        if self._paused or not self.live_enabled or self._adapter is None:
            return
        self._since_last += 1
        if self._since_last < self.every_n:
            return
        self.slot.put(pkt)
        with self._cv:
            self._cv.notify_all()

    def submit_job(self, pkt: FramePacket, tag=None):
        """High-priority one-shot inference (snapshots, still images)."""
        with self._cv:
            self._jobs.append((pkt, tag))
            self._cv.notify_all()

    def stop(self, timeout: float = 10.0):
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        if self.is_alive():
            self.join(timeout)

    # ------------------------------------------------------------ loop
    def _next_work(self):
        with self._cv:
            while not self._stop:
                if self._jobs:
                    pkt, tag = self._jobs.popleft()
                    return pkt, "job", tag
                if not self._paused and self.slot.peek_pending():
                    if self.max_fps > 0:
                        wait = (1.0 / self.max_fps) - (time.perf_counter() - self._last_t)
                        if wait > 0:
                            self._cv.wait(wait)
                            continue
                    pkt = self.slot.take()
                    if pkt is not None:
                        return pkt, "live", None
                self._cv.wait(0.25)
        return None, None, None

    def run(self):
        while True:
            pkt, kind, tag = self._next_work()
            if pkt is None:
                break
            with self._busy:
                adapter = self._adapter
                if adapter is None or adapter.info is None:
                    continue
                s = self.settings()
                t0 = time.perf_counter()
                try:
                    dets = adapter.predict(pkt.image, s)
                except Exception as e:
                    log.exception("inference failed")
                    if self.on_error:
                        self.on_error(f"inference ล้มเหลว: {e}")
                    continue
                ms = (time.perf_counter() - t0) * 1000
                info = adapter.info
                h, w = pkt.image.shape[:2]
                res = DetectionResult(pkt.frame_id, pkt.timestamp, (w, h), dets, ms,
                                      info.identity, s, info.device)
            if kind == "live":
                self._since_last = 0
                self._last_t = time.perf_counter()
                self.infer_fps.tick()
                self.last_ms = ms
            if self.on_result:
                try:
                    self.on_result(pkt, res, kind, tag)
                except Exception:  # pragma: no cover
                    log.exception("result callback failed")
