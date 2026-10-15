"""Frame sources produce FramePacket objects through plain callbacks.

The UI wraps the callbacks into Qt signals (queued across threads), which keeps
sources and the inference pipeline testable without a GUI.
"""
from __future__ import annotations

import collections
import itertools
import threading
import time
from dataclasses import dataclass, field

from ..core.types import FramePacket


class FpsMeter:
    def __init__(self, window: int = 30):
        self._t = collections.deque(maxlen=window)
        self._lock = threading.Lock()

    def tick(self, t: float | None = None):
        with self._lock:
            self._t.append(time.perf_counter() if t is None else t)

    @property
    def fps(self) -> float:
        with self._lock:
            if len(self._t) < 2:
                return 0.0
            span = self._t[-1] - self._t[0]
            if span <= 0 or time.perf_counter() - self._t[-1] > 2.0:
                return 0.0
            return (len(self._t) - 1) / span

    def reset(self):
        with self._lock:
            self._t.clear()


@dataclass
class SourceDescriptor:
    """Something the user can pick in the camera/source list."""
    kind: str                 # "qt-camera" | "opencv-index" | "rtsp" | "video" | "image"
    name: str
    ident: str = ""           # stable identifier (Qt device id hex, index:backend, url key…)
    detail: str = ""          # extra text shown to the user (short id, position…)
    backend: str = ""
    extra: dict = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.kind}|{self.ident}"


class FrameSource:
    kind = "base"

    def __init__(self, label: str = ""):
        self.label = label
        self.on_frame = None          # callable(FramePacket)
        self.on_status = None         # callable(str)
        self.on_error = None          # callable(str)
        self.on_stopped = None        # callable()
        self.capture_fps = FpsMeter()
        self.actual_resolution = None  # (w, h)
        self.actual_fps = None
        self._ids = itertools.count(1)
        self._running = False

    # --------------------------------------------------- interface
    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    @property
    def running(self) -> bool:
        return self._running

    def supports_pause(self) -> bool:
        return False

    # --------------------------------------------------- helpers
    def _emit_frame(self, image):
        self.capture_fps.tick()
        h, w = image.shape[:2]
        self.actual_resolution = (w, h)
        pkt = FramePacket.make(next(self._ids), image, self.label)
        cb = self.on_frame
        if cb:
            cb(pkt)

    def _status(self, msg: str):
        if self.on_status:
            self.on_status(msg)

    def _error(self, msg: str):
        if self.on_error:
            self.on_error(msg)

    def _stopped(self):
        self._running = False
        self.capture_fps.reset()
        if self.on_stopped:
            self.on_stopped()
