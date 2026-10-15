"""Still images: a single file or a folder of JPG/JPEG/PNG files."""
from __future__ import annotations

import os

from ..core.imageops import imread_unicode, list_images
from .base import FrameSource


class ImageSource(FrameSource):
    kind = "image"

    def __init__(self, paths: list, label: str = ""):
        if not paths:
            raise ValueError("ไม่มีไฟล์ภาพ (รองรับ .jpg .jpeg .png)")
        super().__init__(label or os.path.basename(paths[0]))
        self.paths = list(paths)
        self.index = 0

    @classmethod
    def from_path(cls, path: str) -> "ImageSource":
        if os.path.isdir(path):
            files = list_images(path)
            if not files:
                raise ValueError("โฟลเดอร์นี้ไม่มีไฟล์ภาพ .jpg .jpeg .png")
            return cls(files, os.path.basename(path.rstrip("\\/")))
        return cls([path], os.path.basename(path))

    @property
    def current_path(self) -> str:
        return self.paths[self.index]

    def position_text(self) -> str:
        return f"{self.index + 1}/{len(self.paths)}"

    def start(self):
        self._running = True
        self.emit_current()

    def emit_current(self):
        try:
            img = imread_unicode(self.current_path)
        except Exception as e:
            self._error(str(e))
            return
        self.label = os.path.basename(self.current_path)
        self._emit_frame(img)
        self._status(f"ภาพ {self.position_text()}: {self.label}")

    def step(self, delta: int):
        if not self.paths:
            return
        self.index = (self.index + delta) % len(self.paths)
        self.emit_current()

    def stop(self):
        if self._running:
            self._stopped()
