"""Adapter for Ultralytics YOLOv8 / YOLO11 detection checkpoints (.pt).

* Loading a .pt file un-pickles Python objects — only open files from trusted
  sources (the UI asks the user before loading). We never pip-install or run
  code shipped with the model: Ultralytics auto-install / online checks are
  disabled via environment variables before the package is imported.
* Tested families: YOLOv8 and YOLO11 detect models. Other Ultralytics detect
  checkpoints may run inference but are flagged as untested and Grad-CAM is
  disabled for them.
"""
from __future__ import annotations

import logging
import os
import time

import numpy as np

from ..core.classes import ClassRegistry, SOURCE_MODEL, normalize_names, ClassMappingError
from ..core.types import AdapterCapabilities, Detection, InferenceSettings
from .base import (DeviceUnavailableError, ModelAdapter, ModelInfo, ModelLoadError,
                   UnsupportedModelError)

log = logging.getLogger(__name__)

TESTED_FAMILIES = ("yolov8", "yolo11")


def _prepare_ultralytics_env():
    # Must run before ``import ultralytics``.
    os.environ.setdefault("YOLO_OFFLINE", "True")        # no network calls / downloads
    os.environ.setdefault("YOLO_AUTOINSTALL", "False")   # never pip install at runtime
    os.environ.setdefault("YOLO_VERBOSE", "False")
    os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(
        os.environ.get("VMI_DATA_DIR") or os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "VisionModelInspector"),
        "ultralytics"))


def resolve_torch_device(requested: str) -> str:
    import torch
    req = (requested or "auto").lower()
    if req == "auto":
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    if req.startswith("cuda"):
        if not torch.cuda.is_available():
            raise DeviceUnavailableError(
                "เลือก CUDA แต่ใช้งานไม่ได้ (PyTorch รุ่น CPU หรือไม่พบไดรเวอร์ NVIDIA) — "
                "แนะนำให้เปลี่ยนเป็น CPU")
        return req if ":" in req else "cuda:0"
    return "cpu"


def model_family(model) -> str:
    try:
        yaml_file = str(getattr(model, "yaml", {}).get("yaml_file", "")).lower()
    except Exception:
        yaml_file = ""
    for fam in ("yolo11", "yolov8", "yolov10", "yolo12", "yolo26", "yolov5", "yolov9", "rtdetr"):
        if fam in yaml_file:
            return fam
    return yaml_file or "unknown"


class UltralyticsAdapter(ModelAdapter):
    key = "ultralytics-pt"
    display_name = "Ultralytics YOLO (.pt)"
    formats = (".pt",)

    def __init__(self):
        super().__init__()
        self.yolo = None
        self.device = "cpu"
        self.path = ""
        self._gradcam = None
        self._nc = None

    def load(self, path: str, device: str = "auto") -> ModelInfo:
        if not os.path.isfile(path):
            raise ModelLoadError(f"ไม่พบไฟล์: {path}")
        _prepare_ultralytics_env()
        try:
            import torch  # noqa: F401
            from ultralytics import YOLO
        except Exception as e:  # pragma: no cover - packaging problem
            raise ModelLoadError(f"ไม่พบ PyTorch/Ultralytics ในโปรแกรม: {e}") from e

        identity = self.make_identity(path, self.key)
        self.device = resolve_torch_device(device)
        try:
            yolo = YOLO(identity.path, task=None)
        except Exception as e:
            raise UnsupportedModelError(
                "เปิดไฟล์ .pt นี้ไม่ได้ — รองรับเฉพาะ checkpoint ของ Ultralytics YOLO "
                f"(YOLOv8/YOLO11 detect)\nรายละเอียด: {type(e).__name__}: {e}") from e
        if getattr(yolo, "task", None) != "detect":
            raise UnsupportedModelError(
                f"โมเดลนี้เป็น task '{getattr(yolo, 'task', '?')}' — รุ่นนี้รองรับเฉพาะ Object Detection")
        net = yolo.model
        head = net.model[-1] if hasattr(net, "model") else None
        head_name = type(head).__name__ if head is not None else "?"
        nc = int(getattr(head, "nc", 0) or 0)
        fam = model_family(net)

        # ---- classes from model metadata (priority 1)
        limitations = []
        try:
            names = normalize_names(yolo.names)
            reg = ClassRegistry(names, SOURCE_MODEL, count_verified=bool(nc))
        except ClassMappingError as e:
            reg = ClassRegistry.generated(nc, verified=bool(nc))
            reg.notes.append(f"metadata ชื่อคลาสในโมเดลใช้ไม่ได้: {e}")
        if nc and reg.count != nc:
            raise UnsupportedModelError(
                f"metadata ขัดกัน: model.names มี {reg.count} ชื่อ แต่ head ของโมเดลมี {nc} คลาส")
        if reg.looks_generic():
            reg.notes.append("ชื่อคลาสในโมเดลเป็นตัวเลข/ชื่อทั่วไป อาจไม่ใช่ชื่อจริงตอนฝึก — "
                             "นำเข้า data.yaml / classes.txt ได้ที่หน้าจัดการคลาส")
        self._nc = nc or reg.count

        # ---- move + warm-up (checks the device really works)
        self.yolo = yolo
        self.path = identity.path
        try:
            self._predict_raw(np.zeros((64, 64, 3), np.uint8), InferenceSettings(imgsz=64))
        except Exception as e:
            self.close()
            msg = str(e)
            if "out of memory" in msg.lower():
                raise DeviceUnavailableError(
                    "หน่วยความจำ GPU ไม่พอ — แนะนำให้ใช้ CPU หรือลดขนาด input") from e
            raise ModelLoadError(f"ทดสอบ inference ไม่สำเร็จบน {self.device}: {e}") from e

        tested = fam in TESTED_FAMILIES
        if not tested:
            limitations.append(f"ตระกูลโมเดล '{fam}' ยังไม่ได้ทดสอบกับโปรแกรมนี้ (ทดสอบแล้ว: YOLOv8, YOLO11)")
        grad_ok = tested and head_name == "Detect" and not getattr(head, "end2end", False)
        grad_reason = "" if grad_ok else (
            f"ปิด Grad-CAM: รองรับเฉพาะ head 'Detect' ของ YOLOv8/YOLO11 (พบ {head_name}, {fam})")
        stride = int(max(getattr(net, "stride", [32]))) if hasattr(net, "stride") else 32
        caps = AdapterCapabilities(
            task="detect", formats=self.formats, grad_cam=grad_ok, grad_cam_reason=grad_reason,
            input_shape=None, dynamic_input=True, stride=stride,
            output_layout="Ultralytics predictor (NMS ภายใน)", limitations=limitations)
        self.info = ModelInfo(
            identity=identity, caps=caps, classes=reg, device=self.device, inference_ready=True,
            gradcam_status="พร้อมใช้งาน" if grad_ok else grad_reason,
            details={"ตระกูลโมเดล": fam, "Head": head_name,
                     "Letterbox": "Ultralytics LetterBox (auto/min-rect, pad 114)"})
        log.info("loaded %s (%s, nc=%s, device=%s, sha=%s)", identity.name, fam, nc,
                 self.device, identity.short_hash)
        return self.info

    def output_class_count(self):
        return self._nc

    def _predict_raw(self, image_bgr, s: InferenceSettings):
        return self.yolo.predict(source=image_bgr, conf=s.conf, iou=s.iou,
                                 imgsz=self.valid_imgsz(s.imgsz) if self.info else s.imgsz,
                                 max_det=s.max_det, device=self.device, verbose=False, half=False)

    def predict(self, image_bgr: np.ndarray, settings: InferenceSettings) -> list:
        if self.yolo is None:
            raise RuntimeError("ยังไม่ได้โหลดโมเดล")
        with self.lock:
            res = self._predict_raw(image_bgr, settings)[0]
        boxes = res.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy().astype(np.float64)
        conf = boxes.conf.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        return [Detection(i, int(c), float(p), tuple(map(float, b)))
                for i, (b, p, c) in enumerate(zip(xyxy, conf, cls))]

    def gradcam_engine(self):
        if not (self.info and self.info.caps.grad_cam):
            return None
        if self._gradcam is None:
            from ..gradcam.ultralytics_gradcam import UltralyticsGradCAM
            self._gradcam = UltralyticsGradCAM(self)
        return self._gradcam

    def close(self):
        with self.lock:
            if self._gradcam is not None:
                self._gradcam.release()
                self._gradcam = None
            self.yolo = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        import gc
        gc.collect()

    # used by tests to measure end-to-end latency
    def timed_predict(self, image_bgr, settings):
        t = time.perf_counter()
        d = self.predict(image_bgr, settings)
        return d, (time.perf_counter() - t) * 1000
