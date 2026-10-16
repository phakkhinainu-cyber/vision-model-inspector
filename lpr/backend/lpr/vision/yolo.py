"""ตัวตรวจจับวัตถุ YOLO (v8/11 ที่ส่งออกเป็น ONNX) — ใช้ทั้งตรวจจับรถและตรวจจับป้าย"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .runtime import make_session


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    cls: int

    @property
    def box(self) -> np.ndarray:
        return np.array([self.x1, self.y1, self.x2, self.y2], dtype=np.float32)

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1


def letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple[int, int]]:
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR if r > 1 else cv2.INTER_AREA)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas, r, (left, top)


class YoloDetector:
    def __init__(self, path: Path, device: str = "auto", threads: int = 0, imgsz: int | None = None) -> None:
        self.sess = make_session(path, device, threads)
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        shape = inp.shape
        self.imgsz = imgsz or (int(shape[2]) if isinstance(shape[2], int) else 640)
        self.provider = self.sess.get_providers()[0]

    def detect(self, img_bgr: np.ndarray, conf: float = 0.3, classes: set[int] | None = None,
               iou: float = 0.45, max_det: int = 50) -> list[Detection]:
        if img_bgr is None or img_bgr.size == 0:
            return []
        lb, r, (left, top) = letterbox(img_bgr, self.imgsz)
        x = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = x.transpose(2, 0, 1)[None]
        out = self.sess.run(None, {self.input_name: x})[0][0]  # (4+nc, N)
        if out.shape[0] > out.shape[1]:
            out = out.T
        boxes = out[:4].T
        scores_all = out[4:].T
        cls = scores_all.argmax(1)
        scores = scores_all[np.arange(len(cls)), cls]
        keep = scores >= conf
        if classes is not None:
            keep &= np.isin(cls, list(classes))
        if not keep.any():
            return []
        boxes, scores, cls = boxes[keep], scores[keep], cls[keep]
        xywh = boxes.copy()
        xywh[:, 0] -= xywh[:, 2] / 2
        xywh[:, 1] -= xywh[:, 3] / 2
        idx = cv2.dnn.NMSBoxesBatched(xywh.tolist(), scores.tolist(), cls.tolist(), conf, iou)
        idx = np.array(idx).reshape(-1)[:max_det]
        h, w = img_bgr.shape[:2]
        dets = []
        for i in idx:
            x0, y0, bw, bh = xywh[i]
            x1 = float(np.clip((x0 - left) / r, 0, w - 1))
            y1 = float(np.clip((y0 - top) / r, 0, h - 1))
            x2 = float(np.clip((x0 + bw - left) / r, 0, w - 1))
            y2 = float(np.clip((y0 + bh - top) / r, 0, h - 1))
            if x2 - x1 > 2 and y2 - y1 > 2:
                dets.append(Detection(x1, y1, x2, y2, float(scores[i]), int(cls[i])))
        return dets


COCO_VEHICLES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
