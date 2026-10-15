"""Model adapter interface.

An adapter wraps one family of model files and declares — up front — what it
can do (task, formats, input constraints, class metadata, Grad-CAM support).
The rest of the program only talks to this interface, so adding e.g. a
segmentation or classification adapter later does not touch the UI.

How to add an adapter: see docs/ADAPTERS_TH.md.
"""
from __future__ import annotations

import abc
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..core.classes import ClassRegistry
from ..core.sysinfo import file_sha256
from ..core.types import AdapterCapabilities, InferenceSettings, ModelIdentity


class ModelLoadError(RuntimeError):
    """Model cannot be opened by this adapter (message is user-facing Thai)."""


class UnsupportedModelError(ModelLoadError):
    pass


class DeviceUnavailableError(ModelLoadError):
    """Requested device (e.g. CUDA) cannot be used; the UI offers CPU instead."""


@dataclass
class ModelInfo:
    identity: ModelIdentity
    caps: AdapterCapabilities
    classes: ClassRegistry
    device: str                         # device actually used
    inference_ready: bool
    gradcam_status: str                 # user-facing status text
    details: dict = field(default_factory=dict)

    def summary_rows(self) -> list:
        from ..core.classes import SOURCE_LABELS_TH
        c = self.caps
        rows = [
            ("ชื่อไฟล์", self.identity.name),
            ("ชนิดไฟล์", self.identity.file_format),
            ("SHA-256", self.identity.sha256),
            ("Adapter", self.identity.adapter),
            ("Task", c.task),
            ("Input shape", str(c.input_shape) if c.input_shape else "dynamic (กำหนดขนาด input ได้)"),
            ("Output layout", c.output_layout or "-"),
            ("จำนวนคลาส", f"{self.classes.count}" + ("" if self.classes.count_verified
                                                    else " (ตรวจกับ output ไม่ได้)")),
            ("แหล่งที่มาของชื่อคลาส", SOURCE_LABELS_TH.get(self.classes.source, self.classes.source)),
            ("อุปกรณ์ประมวลผล", self.device),
            ("สถานะ inference", "พร้อมใช้งาน" if self.inference_ready else "ไม่พร้อม"),
            ("สถานะ Grad-CAM", self.gradcam_status),
        ]
        for k, v in self.details.items():
            rows.append((k, str(v)))
        return rows


class ModelAdapter(abc.ABC):
    key: str = "base"
    display_name: str = "base"
    formats: tuple = ()

    def __init__(self):
        # Every call into the underlying model goes through this lock so that
        # live inference and Grad-CAM never use the model concurrently.
        self.lock = threading.RLock()
        self.info: Optional[ModelInfo] = None

    # -------------------------------------------------- discovery
    @classmethod
    def can_handle(cls, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in cls.formats

    # -------------------------------------------------- lifecycle
    @abc.abstractmethod
    def load(self, path: str, device: str = "auto") -> ModelInfo:
        ...

    @abc.abstractmethod
    def predict(self, image_bgr: np.ndarray, settings: InferenceSettings) -> list:
        """Return list[Detection] in original image coordinates."""

    def close(self):
        """Release model resources (GPU memory, sessions)."""

    # -------------------------------------------------- classes
    def output_class_count(self) -> Optional[int]:
        """Number of classes the model output really has (None if unknown)."""
        return None

    def set_class_registry(self, reg: ClassRegistry):
        if self.info is not None:
            self.info.classes = reg

    # -------------------------------------------------- Grad-CAM
    def gradcam_engine(self):
        """Return an object with ``layer_options()`` and ``compute(...)`` or None."""
        return None

    # -------------------------------------------------- helpers
    @staticmethod
    def make_identity(path: str, adapter_key: str) -> ModelIdentity:
        path = os.path.abspath(path)
        return ModelIdentity(name=os.path.basename(path), path=path, sha256=file_sha256(path),
                             adapter=adapter_key, file_format=os.path.splitext(path)[1].lower())

    def valid_imgsz(self, imgsz: int) -> int:
        caps = self.info.caps if self.info else None
        if caps and not caps.dynamic_input and caps.input_shape:
            return int(caps.input_shape[-1])
        stride = caps.stride if caps else 32
        return max(stride, int(round(imgsz / stride)) * stride)
