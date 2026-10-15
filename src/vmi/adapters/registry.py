"""Choose an adapter for a model file. Register new adapters in ``ADAPTERS``."""
from __future__ import annotations

import os

from .base import ModelAdapter, UnsupportedModelError


def _adapters():
    from .ultralytics_adapter import UltralyticsAdapter
    from .onnx_adapter import OnnxYoloAdapter
    return [UltralyticsAdapter, OnnxYoloAdapter]


def supported_extensions() -> list:
    exts = []
    for a in _adapters():
        exts.extend(a.formats)
    return exts


def create_adapter(path: str) -> ModelAdapter:
    for cls in _adapters():
        if cls.can_handle(path):
            return cls()
    ext = os.path.splitext(path)[1].lower() or "(ไม่มีนามสกุล)"
    raise UnsupportedModelError(f"ไม่รองรับไฟล์ชนิด {ext} — รองรับ: {', '.join(supported_extensions())}")
