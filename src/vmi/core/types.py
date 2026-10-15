"""Normalized data types shared by every adapter, source and UI component.

All bounding boxes are stored in *original image pixel coordinates* as
(x1, y1, x2, y2) floats. Adapters are responsible for undoing any
letterbox/resize before returning detections.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np


def format_confidence(value: float) -> str:
    """Single place that formats confidences so the whole app is consistent."""
    return f"{float(value):.2f}"


@dataclass(frozen=True)
class ModelIdentity:
    name: str            # file name, e.g. "yolov8n.pt"
    path: str            # absolute path at load time
    sha256: str          # full hex digest of the file
    adapter: str         # adapter key, e.g. "ultralytics-pt"
    file_format: str     # ".pt" / ".onnx"

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InferenceSettings:
    conf: float = 0.25
    iou: float = 0.45
    imgsz: int = 640
    max_det: int = 300
    device: str = "auto"         # requested device: auto / cpu / cuda:0

    def copy(self) -> "InferenceSettings":
        return InferenceSettings(**asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Detection:
    det_id: int                  # index within one result (stable for a snapshot)
    class_id: int
    confidence: float
    box: tuple                   # (x1, y1, x2, y2) in original image pixels

    @property
    def xywh(self) -> tuple:
        x1, y1, x2, y2 = self.box
        return (x1, y1, x2 - x1, y2 - y1)

    def xywh_int(self) -> tuple:
        x, y, w, h = self.xywh
        return (int(round(x)), int(round(y)), int(round(w)), int(round(h)))

    def to_dict(self) -> dict:
        return {
            "det_id": self.det_id,
            "class_id": int(self.class_id),
            "confidence": float(self.confidence),
            "box_xyxy": [float(v) for v in self.box],
        }


@dataclass
class DetectionResult:
    frame_id: int
    timestamp: float
    image_size: tuple            # (width, height) of the image that was analysed
    detections: list
    inference_ms: float
    model: ModelIdentity
    settings: InferenceSettings
    device: str                  # device actually used

    def to_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "image_size": list(self.image_size),
            "inference_ms": self.inference_ms,
            "device": self.device,
            "model": self.model.to_dict(),
            "settings": self.settings.to_dict(),
            "detections": [d.to_dict() for d in self.detections],
        }


@dataclass
class FramePacket:
    """One frame coming from a source. ``image`` is BGR uint8 (H, W, 3)."""
    frame_id: int
    timestamp: float
    image: np.ndarray
    source_label: str = ""

    @staticmethod
    def make(frame_id: int, image: np.ndarray, source_label: str = "") -> "FramePacket":
        return FramePacket(frame_id, time.time(), image, source_label)


@dataclass
class AdapterCapabilities:
    task: str                                # "detect"
    formats: tuple                           # (".pt",)
    grad_cam: bool
    grad_cam_reason: str = ""                # why not supported / notes
    input_shape: Optional[tuple] = None      # (1, 3, H, W) or None if dynamic
    dynamic_input: bool = True
    supported_imgsz: tuple = ()              # allowed sizes; empty = any multiple of stride
    stride: int = 32
    output_layout: str = ""
    limitations: list = field(default_factory=list)
