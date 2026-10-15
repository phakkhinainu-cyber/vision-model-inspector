"""USB / built-in cameras via Qt Multimedia.

Devices are enumerated *and opened* through the same backend (Qt Multimedia)
using the real device identifier, so there is no assumption that Qt's list
order matches OpenCV indices. The identifier is stable across restarts on
Windows (it is the device symbolic link), which is what we store as the
preferred camera.
"""
from __future__ import annotations

import logging
import re

import cv2
import numpy as np
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (QCamera, QCameraDevice, QMediaCaptureSession, QMediaDevices,
                                  QVideoSink)

from .base import FrameSource, SourceDescriptor

log = logging.getLogger(__name__)

_VIDPID = re.compile(r"vid_([0-9a-f]{4}).*?pid_([0-9a-f]{4})", re.IGNORECASE)


def _raw_id(dev: QCameraDevice) -> str:
    try:
        return bytes(dev.id().data()).decode("utf-8", "replace")
    except Exception:
        return str(dev.id())


def _format_list(dev: QCameraDevice) -> list:
    seen, out = set(), []
    for f in dev.videoFormats():
        r = f.resolution()
        key = (r.width(), r.height(), round(f.maxFrameRate(), 1))
        if key in seen or r.width() <= 0:
            continue
        seen.add(key)
        out.append({"w": r.width(), "h": r.height(), "min_fps": f.minFrameRate(),
                    "max_fps": f.maxFrameRate(), "pixel": str(f.pixelFormat()).split(".")[-1]})
    out.sort(key=lambda d: (d["w"] * d["h"], d["max_fps"]), reverse=True)
    return out


def list_qt_cameras() -> list:
    devs = list(QMediaDevices.videoInputs())
    descs = [d.description() for d in devs]
    out = []
    for d in devs:
        raw = _raw_id(d)
        ident = bytes(d.id().data()).hex()
        m = _VIDPID.search(raw)
        kind = "USB" if ("usb" in raw.lower() or m) else "ในเครื่อง/อื่น ๆ"
        pos = {QCameraDevice.Position.FrontFace: "กล้องหน้า",
               QCameraDevice.Position.BackFace: "กล้องหลัง"}.get(d.position(), "")
        short = (f"VID_{m.group(1).upper()} PID_{m.group(2).upper()}" if m else "") or f"…{raw[-10:]}"
        name = d.description()
        if descs.count(name) > 1:
            name = f"{name} [{raw[-8:]}]"
        detail = " · ".join(x for x in (kind, pos, short, "ค่าเริ่มต้นของระบบ" if d.isDefault() else "") if x)
        out.append(SourceDescriptor("qt-camera", name, ident, detail, "Qt Multimedia",
                                    {"formats": _format_list(d), "raw_id": raw, "type": kind}))
    return out


def find_qt_device(ident_hex: str):
    for d in QMediaDevices.videoInputs():
        if bytes(d.id().data()).hex() == ident_hex:
            return d
    return None


def qimage_to_bgr(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)
    rgb = buf[:, : w * 3].reshape(h, w, 3)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)   # also makes an owned copy


class QtCameraSource(FrameSource):
    kind = "qt-camera"

    def __init__(self, ident_hex: str, label: str, fmt: dict | None = None,
                 first_frame_timeout: float = 8.0, parent: QObject | None = None):
        super().__init__(label)
        self.ident = ident_hex
        self.fmt = fmt
        self.timeout = first_frame_timeout
        self._parent = parent
        self._cam = self._session = self._sink = self._timer = self._devices = None
        self._got_frame = False

    def start(self):
        if self._running:
            return
        dev = find_qt_device(self.ident)
        if dev is None:
            self._error(f"ไม่พบกล้อง '{self.label}' — อาจถูกถอดออก กรุณาเลือกกล้องใหม่")
            return
        self._cam = QCamera(dev, self._parent)
        if self.fmt:
            best = None
            for f in dev.videoFormats():
                r = f.resolution()
                if (r.width(), r.height()) == (self.fmt.get("w"), self.fmt.get("h")):
                    if best is None or abs(f.maxFrameRate() - self.fmt.get("max_fps", 30)) < \
                            abs(best.maxFrameRate() - self.fmt.get("max_fps", 30)):
                        best = f
            if best is not None:
                self._cam.setCameraFormat(best)
        self._session = QMediaCaptureSession(self._parent)
        self._sink = QVideoSink(self._parent)
        self._session.setCamera(self._cam)
        self._session.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._cam.errorOccurred.connect(self._on_error)
        self._devices = QMediaDevices(self._parent)
        self._devices.videoInputsChanged.connect(self._check_present)
        self._timer = QTimer(self._parent)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._got_frame = False
        self._running = True
        self._status(f"กำลังเปิดกล้อง {self.label} …")
        self._cam.start()
        self._timer.start(int(self.timeout * 1000))

    def _on_frame(self, frame):
        if not self._running:
            return
        try:
            img = frame.toImage()
        except Exception:
            return
        if img.isNull():
            return
        if not self._got_frame:
            self._got_frame = True
            if self._timer:
                self._timer.stop()
            f = self._cam.cameraFormat() if self._cam else None
            if f is not None and not f.isNull():
                self.actual_fps = f.maxFrameRate()
            self._status("เชื่อมต่อแล้ว")
        self._emit_frame(qimage_to_bgr(img))

    def _on_error(self, err, text=""):
        if err == QCamera.Error.NoError:
            return
        msg = text or str(err)
        self._error(f"กล้องขัดข้อง: {msg} — อาจถูกใช้งานโดยโปรแกรมอื่น หรือถูกปิดสิทธิ์กล้องใน "
                    "Windows (Settings › Privacy & security › Camera)")
        self.stop()

    def _on_timeout(self):
        if self._running and not self._got_frame:
            self._error("เปิดกล้องไม่สำเร็จภายในเวลาที่กำหนด (timeout) — กล้องอาจถูกใช้งานอยู่ "
                        "หรือ Windows ปิดสิทธิ์การเข้าถึงกล้อง")
            self.stop()

    def _check_present(self):
        if self._running and find_qt_device(self.ident) is None:
            self._error(f"กล้อง '{self.label}' ถูกถอดออก — หยุดรับภาพแล้ว (ไม่สลับไปกล้องอื่นอัตโนมัติ)")
            self.stop()

    def stop(self):
        if self._timer:
            self._timer.stop()
        was = self._running
        self._running = False
        try:
            if self._sink is not None:
                self._sink.videoFrameChanged.disconnect(self._on_frame)
        except (RuntimeError, TypeError):
            pass
        if self._cam is not None:
            try:
                self._cam.stop()
            except RuntimeError:
                pass
        for obj in (self._timer, self._devices, self._sink, self._session, self._cam):
            if obj is not None:
                obj.deleteLater()
        self._cam = self._session = self._sink = self._timer = self._devices = None
        if was:
            self._stopped()
