"""OpenCV based sources: video files, manual camera index/backend, RTSP.

Every capture runs in its own thread. Opening is guarded by a timeout so a
camera that is busy / blocked by Windows privacy settings never freezes the
UI; the device handle is always released, also after a timeout.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import cv2

from ..config import redact
from .base import FrameSource

log = logging.getLogger(__name__)

BACKENDS = {
    "auto": cv2.CAP_ANY,
    "dshow": getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY),
    "msmf": getattr(cv2, "CAP_MSMF", cv2.CAP_ANY),
    "v4l2": getattr(cv2, "CAP_V4L2", cv2.CAP_ANY),
    "ffmpeg": cv2.CAP_FFMPEG,
}


def windows_safe_path(path: str) -> str:
    """OpenCV's video backends on Windows may not accept non-ASCII paths.

    Use the 8.3 short path (pure ASCII) when the long path has Thai/other
    characters. Returns the path unchanged elsewhere or when unavailable.
    """
    if os.name != "nt" or path.isascii():
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
        if 0 < n < len(buf) and buf.value.isascii():
            return buf.value
    except Exception:
        pass
    return path


def open_capture(target, backend: int, timeout_s: float, params=None, cancel: threading.Event = None):
    """Open cv2.VideoCapture in a helper thread. Returns (cap or None, error text)."""
    box = {}

    def worker():
        try:
            cap = cv2.VideoCapture(target, backend, params or [])
            box["cap"] = cap
        except Exception as e:  # pragma: no cover
            box["err"] = str(e)

    th = threading.Thread(target=worker, daemon=True, name="cv-open")
    th.start()
    deadline = time.time() + timeout_s
    while th.is_alive() and time.time() < deadline:
        if cancel is not None and cancel.is_set():
            break
        th.join(0.05)
    if th.is_alive():
        # release whenever the stuck open finally returns
        def reaper():
            th.join()
            c = box.get("cap")
            if c is not None:
                c.release()
        threading.Thread(target=reaper, daemon=True, name="cv-reaper").start()
        if cancel is not None and cancel.is_set():
            return None, "ยกเลิกแล้ว"
        return None, f"เปิดแหล่งภาพไม่สำเร็จภายใน {timeout_s:.0f} วินาที (timeout)"
    if "err" in box:
        return None, box["err"]
    cap = box.get("cap")
    if cap is None or not cap.isOpened():
        if cap is not None:
            cap.release()
        return None, "เปิดแหล่งภาพไม่ได้ (อุปกรณ์อาจถูกใช้งานโดยโปรแกรมอื่น ถูกถอด หรือถูกปิดสิทธิ์กล้องใน Windows)"
    return cap, ""


class OpenCVSource(FrameSource):
    """kind: 'video' (file path), 'opencv-index' (int index) or 'rtsp' (URL)."""

    def __init__(self, kind: str, target, label: str, backend: str = "auto",
                 open_timeout: float = 8.0, reconnects: int = 3, width: int = 0, height: int = 0,
                 fps: float = 0, loop_video: bool = False):
        super().__init__(label)
        self.kind = kind
        self.target = target
        self.backend_name = backend
        self.open_timeout = open_timeout
        self.reconnects = reconnects if kind == "rtsp" else 0
        self.req_w, self.req_h, self.req_fps = width, height, fps
        self.loop_video = loop_video
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread = None
        self.frame_count = 0
        self.position = 0

    def supports_pause(self) -> bool:
        return self.kind == "video"

    def set_paused(self, paused: bool):
        (self._pause.set if paused else self._pause.clear)()

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    def start(self):
        if self._running:
            return
        if self.kind == "video" and not os.path.isfile(self.target):
            self._error(f"ไม่พบไฟล์วิดีโอ: {self.target}")
            return
        self._stop.clear()
        self._pause.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"src-{self.kind}")
        self._thread.start()

    def stop(self, wait: float = 5.0):
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(wait)
        self._thread = None

    # ------------------------------------------------------------------
    def _open(self):
        backend = BACKENDS.get(self.backend_name, cv2.CAP_ANY)
        params = []
        if self.kind == "rtsp":
            backend = cv2.CAP_FFMPEG
            to = int(self.open_timeout * 1000)
            params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, to, cv2.CAP_PROP_READ_TIMEOUT_MSEC, to]
        target = self.target
        if self.kind == "video":
            backend = cv2.CAP_ANY
            target = windows_safe_path(target)
        cap, err = open_capture(target, backend, self.open_timeout + 2, params, self._stop)
        if cap is None:
            return None, err
        if self.kind == "opencv-index":
            if self.req_w and self.req_h:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.req_w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.req_h)
            if self.req_fps:
                cap.set(cv2.CAP_PROP_FPS, self.req_fps)
        self.actual_fps = cap.get(cv2.CAP_PROP_FPS) or None
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        return cap, ""

    def _run(self):
        attempts = 0
        cap = None
        try:
            while not self._stop.is_set():
                self._status(f"กำลังเชื่อมต่อ {redact(str(self.label))} …")
                cap, err = self._open()
                if cap is None:
                    attempts += 1
                    if self._stop.is_set():
                        break
                    if attempts > self.reconnects:
                        self._error(err)
                        break
                    self._status(f"เชื่อมต่อไม่สำเร็จ ลองใหม่ ({attempts}/{self.reconnects}) …")
                    self._stop.wait(min(2.0 * attempts, 6.0))
                    continue
                attempts = 0
                self._status("เชื่อมต่อแล้ว")
                ended = self._read_loop(cap)
                cap.release()
                cap = None
                if ended == "eof":
                    if self.loop_video and not self._stop.is_set():
                        continue
                    self._status("วิดีโอจบแล้ว")
                    break
                if ended == "lost":
                    attempts += 1
                    if attempts > self.reconnects:
                        self._error("สัญญาณภาพขาดหาย (อุปกรณ์ถูกถอดหรือเครือข่ายขัดข้อง)")
                        break
                    self._status(f"สัญญาณหาย กำลังเชื่อมต่อใหม่ ({attempts}/{self.reconnects}) …")
                    self._stop.wait(1.0)
                    continue
                break
        except Exception as e:  # pragma: no cover
            log.exception("source crashed")
            self._error(f"แหล่งภาพขัดข้อง: {e}")
        finally:
            if cap is not None:
                cap.release()
            self._stopped()

    def _read_loop(self, cap) -> str:
        period = 0.0
        if self.kind == "video":
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            period = 1.0 / max(1.0, min(fps, 120.0))
        fails = 0
        next_t = time.perf_counter()
        while not self._stop.is_set():
            if self._pause.is_set():
                self._stop.wait(0.05)
                next_t = time.perf_counter()
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                if self.kind == "video":
                    return "eof"
                fails += 1
                if fails >= 10:
                    return "lost"
                self._stop.wait(0.05)
                continue
            fails = 0
            if self.kind == "video":
                self.position = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
            self._emit_frame(frame)
            if period:
                next_t += period
                delay = next_t - time.perf_counter()
                if delay > 0:
                    self._stop.wait(delay)
                else:
                    next_t = time.perf_counter()
        return "stopped"
