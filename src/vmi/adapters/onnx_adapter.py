"""Adapter for YOLOv8 / YOLO11 detection models exported to ONNX.

Only output layouts that we can identify with certainty are accepted:

* ``raw``            (1, 4+nc, A)  — Ultralytics export without NMS
* ``raw-transposed`` (1, A, 4+nc)
* ``nms``            (1, N, 6)     — x1, y1, x2, y2, score, class (export with nms=True)

For the raw layouts ``A`` must equal the anchor count of a stride 8/16/32
head for the input size, otherwise the model is rejected with an explanation
(we never guess an unknown layout). Grad-CAM is disabled for ONNX in this
release — use the matching .pt file instead.
"""
from __future__ import annotations

import logging
import os

import numpy as np

from ..core.classes import (ClassMappingError, ClassRegistry, SOURCE_ONNX, parse_literal_names)
from ..core.imageops import letterbox, unletterbox_boxes, yolo_raw_postprocess
from ..core.types import AdapterCapabilities, Detection, InferenceSettings
from .base import (DeviceUnavailableError, ModelAdapter, ModelInfo, ModelLoadError,
                   UnsupportedModelError)

log = logging.getLogger(__name__)

GRADCAM_ONNX_REASON = "ไฟล์ ONNX: ปิด Grad-CAM ในรุ่นแรก — ใช้ไฟล์ .pt (YOLOv8/YOLO11) ที่รองรับแทน"


def expected_anchors(h: int, w: int, strides=(8, 16, 32)) -> int:
    return sum((h // s) * (w // s) for s in strides)


def _ort_providers(requested: str):
    import onnxruntime as ort
    avail = ort.get_available_providers()
    req = (requested or "auto").lower()
    if req.startswith("cuda"):
        if "CUDAExecutionProvider" not in avail:
            raise DeviceUnavailableError(
                "ONNX Runtime ที่ติดตั้งไม่มี CUDAExecutionProvider — แนะนำให้ใช้ CPU")
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if req == "auto" and "CUDAExecutionProvider" in avail:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class OnnxYoloAdapter(ModelAdapter):
    key = "onnx-yolo"
    display_name = "ONNX YOLOv8/YOLO11 detect"
    formats = (".onnx",)

    def __init__(self):
        super().__init__()
        self.session = None
        self.input_name = ""
        self.input_hw = None         # (H, W) if static
        self.input_dtype = np.float32
        self.layout = ""
        self._nc = None
        self.device = "cpu"

    def load(self, path: str, device: str = "auto") -> ModelInfo:
        if not os.path.isfile(path):
            raise ModelLoadError(f"ไม่พบไฟล์: {path}")
        try:
            import onnxruntime as ort
        except Exception as e:  # pragma: no cover
            raise ModelLoadError(f"ไม่พบ ONNX Runtime: {e}") from e
        identity = self.make_identity(path, self.key)
        providers = _ort_providers(device)
        so = ort.SessionOptions()
        so.log_severity_level = 3
        try:
            # read bytes ourselves so Thai paths work on every platform
            with open(identity.path, "rb") as f:
                self.session = ort.InferenceSession(f.read(), sess_options=so, providers=providers)
        except Exception as e:
            raise UnsupportedModelError(f"ONNX Runtime เปิดไฟล์นี้ไม่ได้: {e}") from e
        used = self.session.get_providers()
        self.device = "cuda" if "CUDAExecutionProvider" in used else "cpu"

        ins = self.session.get_inputs()
        if len(ins) != 1:
            raise UnsupportedModelError(f"รองรับโมเดลที่มี input เดียว (พบ {len(ins)})")
        inp = ins[0]
        shape = list(inp.shape)
        if len(shape) != 4 or (isinstance(shape[1], int) and shape[1] != 3):
            raise UnsupportedModelError(f"input shape {shape} ไม่ใช่ภาพ (N, 3, H, W)")
        self.input_name = inp.name
        self.input_dtype = np.float16 if "float16" in inp.type else np.float32
        static = isinstance(shape[2], int) and isinstance(shape[3], int)

        meta = {}
        try:
            meta = dict(self.session.get_modelmeta().custom_metadata_map or {})
        except Exception:
            pass
        task = meta.get("task")
        if task and task != "detect":
            raise UnsupportedModelError(f"metadata ระบุ task='{task}' — รุ่นนี้รองรับเฉพาะ detect")
        try:
            stride = int(float(meta.get("stride", 32)))
        except ValueError:
            stride = 32

        if static:
            self.input_hw = (int(shape[2]), int(shape[3]))
            probe_hw = self.input_hw
        else:
            self.input_hw = None
            probe_hw = (640, 640)

        # ---- probe the real output shape with a blank image
        try:
            out = self._run(np.full((probe_hw[0], probe_hw[1], 3), 114, np.uint8), probe_hw)
        except Exception as e:
            raise UnsupportedModelError(f"รันโมเดลทดสอบไม่ได้: {e}") from e
        oshape = tuple(out.shape)
        meta_names = None
        names_err = None
        if "names" in meta:
            try:
                meta_names = parse_literal_names(meta["names"])
            except ClassMappingError as e:
                names_err = str(e)
        A = expected_anchors(*probe_hw)
        end2end = str(meta.get("end2end", "")).lower() == "true" or str(meta.get("nms", "")).lower() == "true"
        if len(oshape) == 3 and oshape[0] == 1 and oshape[2] == A and oshape[1] > 4 and not end2end:
            self.layout, nc = "raw", oshape[1] - 4
        elif len(oshape) == 3 and oshape[0] == 1 and oshape[1] == A and oshape[2] > 4 and not end2end:
            self.layout, nc = "raw-transposed", oshape[2] - 4
        elif len(oshape) == 3 and oshape[0] == 1 and oshape[2] == 6:
            self.layout, nc = "nms", None
        else:
            raise UnsupportedModelError(
                f"ไม่รู้จักรูปแบบ output {oshape} สำหรับ input {probe_hw} — "
                "รองรับเฉพาะ YOLOv8/YOLO11 detect ที่ export จาก Ultralytics "
                f"((1, 4+nc, {A}) หรือ (1, N, 6))")
        self._nc = nc

        # ---- classes: ONNX metadata first, otherwise generated
        notes = []
        if meta_names is not None:
            if nc is not None and len(meta_names) != nc:
                raise UnsupportedModelError(
                    f"metadata ขัดกับ output: names มี {len(meta_names)} ชื่อ แต่ output มี {nc} คลาส")
            reg = ClassRegistry(meta_names, SOURCE_ONNX, count_verified=nc is not None)
        elif nc is not None:
            reg = ClassRegistry.generated(nc, verified=True)
        else:
            reg = ClassRegistry({}, "generated", count_verified=False)
            reg.notes.append("ไม่มี metadata ชื่อคลาส และ output แบบ NMS ไม่บอกจำนวนคลาส — "
                             "แสดงเป็น class_<id> ตามรหัสที่พบ; นำเข้ารายชื่อได้ที่หน้าจัดการคลาส")
        if names_err:
            reg.notes.append(f"metadata ชื่อคลาสเสีย: {names_err}")
        if nc is None:
            notes.append("output รวม NMS แล้ว: ค่า IoU threshold ของโปรแกรมไม่มีผล")
        if not static:
            notes.append("input แบบ dynamic: ใช้ขนาด input ที่เลือกแบบสี่เหลี่ยมจัตุรัส (letterbox)")

        caps = AdapterCapabilities(
            task="detect", formats=self.formats, grad_cam=False, grad_cam_reason=GRADCAM_ONNX_REASON,
            input_shape=tuple(shape) if static else None, dynamic_input=not static,
            supported_imgsz=(self.input_hw[0],) if static else (), stride=stride,
            output_layout=f"{self.layout} {oshape}", limitations=notes)
        self.info = ModelInfo(
            identity=identity, caps=caps, classes=reg, device=self.device, inference_ready=True,
            gradcam_status=GRADCAM_ONNX_REASON,
            details={"Execution providers": ", ".join(used), "Input dtype": inp.type,
                     "Letterbox": "สี่เหลี่ยมจัตุรัส pad 114 (auto=False)",
                     "Metadata keys": ", ".join(sorted(meta)) or "-"})
        log.info("loaded ONNX %s layout=%s nc=%s providers=%s", identity.name, self.layout, nc, used)
        return self.info

    def output_class_count(self):
        return self._nc

    def _hw(self, imgsz: int):
        if self.input_hw:
            return self.input_hw
        s = self.valid_imgsz(imgsz) if self.info else imgsz
        return (s, s)

    def _run(self, image_bgr, hw):
        lb, _ = letterbox(image_bgr, hw, auto=False)
        return self._infer_letterboxed(lb)

    def _infer_letterboxed(self, lb):
        x = lb[:, :, ::-1].transpose(2, 0, 1)[None].astype(self.input_dtype) / 255.0
        x = np.ascontiguousarray(x, dtype=self.input_dtype)
        return np.asarray(self.session.run(None, {self.input_name: x})[0])

    def predict(self, image_bgr: np.ndarray, settings: InferenceSettings) -> list:
        if self.session is None:
            raise RuntimeError("ยังไม่ได้โหลดโมเดล")
        hw = self._hw(settings.imgsz)
        lb, info = letterbox(image_bgr, hw, auto=False)
        with self.lock:
            out = self._infer_letterboxed(lb).astype(np.float32)
        if self.layout in ("raw", "raw-transposed"):
            pred = out[0] if self.layout == "raw" else out[0].T
            boxes, scores, cls, _ = yolo_raw_postprocess(pred, settings.conf, settings.iou,
                                                         settings.max_det)
        else:
            rows = out[0]
            rows = rows[rows[:, 4] > settings.conf][: settings.max_det]
            boxes, scores, cls = rows[:, :4], rows[:, 4], rows[:, 5].astype(np.int64)
        boxes = unletterbox_boxes(boxes, info)
        return [Detection(i, int(c), float(p), tuple(map(float, b)))
                for i, (b, p, c) in enumerate(zip(boxes, scores, cls))]

    def close(self):
        with self.lock:
            self.session = None
