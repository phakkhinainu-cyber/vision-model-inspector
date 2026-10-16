"""อ่านภาพจากกล้อง RTSP / ไฟล์วิดีโอ (โหมดจำลอง) ใน thread แยก พร้อมเชื่อมต่อใหม่อัตโนมัติเมื่อหลุด

รูปแบบแหล่งภาพ:
- rtsp://user:pass@192.168.1.10:554/stream1   กล้อง IP
- http(s)://.../video.mjpg                      MJPEG/HTTP
- C:\\videos\\gate.mp4 หรือ file:///...          ไฟล์วิดีโอ (เล่นวนตามความเร็วจริง)
- 0, 1, ...                                     กล้อง USB/เว็บแคม
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

log = logging.getLogger(__name__)

# RTSP ผ่าน TCP (ภาพไม่แตก) และ timeout 5 วินาที
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000|timeout;5000000")


def is_file_source(url: str) -> bool:
    u = url.strip()
    if u.startswith("file://"):
        return True
    if "://" in u or u.isdigit():
        return False
    return Path(u).suffix.lower() in (".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4v", ".ts", ".mpg", ".jpg",
                                      ".jpeg", ".png")


def open_capture(url: str) -> cv2.VideoCapture:
    u = url.strip()
    if u.startswith("file://"):
        u = u[7:]
        if os.name == "nt" and u.startswith("/") and len(u) > 2 and u[2] == ":":
            u = u[1:]
    if u.isdigit():
        return cv2.VideoCapture(int(u))
    if u.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return cv2.VideoCapture(u, cv2.CAP_FFMPEG)
    return cv2.VideoCapture(u)


def mask_url(url: str) -> str:
    """ซ่อนรหัสผ่านใน URL ก่อนเขียน log"""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        cred, host = rest.rsplit("@", 1)
        user = cred.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


class StreamReader:
    """เก็บเฉพาะเฟรมล่าสุด (ไม่สะสมคิว เพื่อลดความหน่วง)"""

    def __init__(self, url: str, name: str = "", on_frame: Callable[[np.ndarray, float], None] | None = None,
                 realtime_files: bool = True) -> None:
        self.url = url
        self.name = name or mask_url(url)
        self.on_frame = on_frame
        self.realtime_files = realtime_files
        self.is_file = is_file_source(url)
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._ts = 0.0
        self._seq = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False
        self.last_error = ""
        self.fps = 0.0
        self.size: tuple[int, int] = (0, 0)
        self.reconnects = 0

    def start(self) -> "StreamReader":
        self._thread = threading.Thread(target=self._run, name=f"stream-{self.name}", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def latest(self) -> tuple[np.ndarray | None, float, int]:
        with self._lock:
            return self._frame, self._ts, self._seq

    def wait_new(self, last_seq: int, timeout: float = 0.5) -> tuple[np.ndarray | None, float, int]:
        end = time.monotonic() + timeout
        while time.monotonic() < end and not self._stop.is_set():
            f, ts, seq = self.latest()
            if seq != last_seq and f is not None:
                return f, ts, seq
            time.sleep(0.005)
        return self.latest()

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            # ภาพนิ่ง (ใช้ทดสอบ)
            if self.is_file and Path(self.url).suffix.lower() in (".jpg", ".jpeg", ".png"):
                img = cv2.imread(self.url)
                if img is None:
                    self.last_error = "เปิดไฟล์ภาพไม่ได้"
                    time.sleep(2)
                    continue
                self.connected = True
                self.size = (img.shape[1], img.shape[0])
                while not self._stop.is_set():
                    self._publish(img.copy())
                    time.sleep(0.1)
                return
            cap = open_capture(self.url)
            if not cap.isOpened():
                self.connected = False
                self.last_error = "เชื่อมต่อกล้องไม่ได้"
                log.warning("เชื่อมต่อ %s ไม่ได้ จะลองใหม่ใน %.0f วินาที", self.name, backoff)
                self._stop.wait(backoff)
                backoff = min(30.0, backoff * 2)
                self.reconnects += 1
                continue
            file_fps = cap.get(cv2.CAP_PROP_FPS) or 0
            if not (1 <= file_fps <= 120):
                file_fps = 15.0
            self.connected = True
            self.last_error = ""
            backoff = 1.0
            fails = 0
            t_last = time.monotonic()
            n = 0
            t_start = time.monotonic()
            frame_i = 0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    if self.is_file:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # วนเล่นไฟล์
                        t_start, frame_i = time.monotonic(), 0
                        fails += 1
                        if fails > 3:
                            break
                        continue
                    fails += 1
                    if fails > 25:
                        self.last_error = "ภาพจากกล้องหยุด"
                        break
                    time.sleep(0.04)
                    continue
                fails = 0
                self._publish(frame)
                n += 1
                frame_i += 1
                now = time.monotonic()
                if now - t_last >= 2.0:
                    self.fps = n / (now - t_last)
                    n, t_last = 0, now
                if self.is_file and self.realtime_files:
                    delay = t_start + frame_i / file_fps - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
            cap.release()
            self.connected = False
            if not self._stop.is_set():
                self.reconnects += 1
                log.warning("ภาพจาก %s หลุด กำลังเชื่อมต่อใหม่", self.name)
                self._stop.wait(backoff)

    def _publish(self, frame: np.ndarray) -> None:
        ts = time.time()
        with self._lock:
            self._frame = frame
            self._ts = ts
            self._seq += 1
        self.size = (frame.shape[1], frame.shape[0])
        if self.on_frame is not None:
            try:
                self.on_frame(frame, ts)
            except Exception:  # noqa: BLE001
                log.exception("on_frame failed")


def probe(url: str, timeout: float = 10.0) -> dict:
    """ทดสอบการเชื่อมต่อ: คืนขนาดภาพ, fps และภาพตัวอย่าง (JPEG)"""
    result: dict = {"ok": False}

    def run() -> None:
        cap = open_capture(url)
        if not cap.isOpened():
            result["error"] = "เชื่อมต่อไม่ได้ (ตรวจ IP, พอร์ต, ชื่อผู้ใช้/รหัสผ่าน และลิงก์ RTSP)"
            return
        ok, frame = False, None
        for _ in range(30):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        if not ok or frame is None:
            result["error"] = "เชื่อมต่อได้แต่ไม่ได้รับภาพ"
            cap.release()
            return
        result.update(ok=True, width=int(frame.shape[1]), height=int(frame.shape[0]),
                      fps=float(cap.get(cv2.CAP_PROP_FPS) or 0))
        ok2, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok2:
            result["jpeg"] = jpg.tobytes()
        cap.release()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return {"ok": False, "error": "หมดเวลาเชื่อมต่อ"}
    return result
