"""Pure numpy / OpenCV image helpers (no torch, no Qt).

The letterbox implementation mirrors Ultralytics ``LetterBox`` (center=True,
pad value 114, INTER_LINEAR) so that coordinates computed here line up with
what Ultralytics' predictor does internally. ``unletterbox_boxes`` uses the
*exact* integer padding that was applied, so mapping back is lossless apart
from floating point rounding.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import cv2
import numpy as np

PAD_VALUE = 114


@dataclass(frozen=True)
class LetterboxInfo:
    gain: float          # resize ratio applied to the original image
    pad_left: int
    pad_top: int
    out_w: int           # letterboxed image width
    out_h: int
    orig_w: int
    orig_h: int
    auto: bool
    stride: int

    def to_dict(self) -> dict:
        return {
            "gain": self.gain, "pad_left": self.pad_left, "pad_top": self.pad_top,
            "out_size": [self.out_w, self.out_h], "orig_size": [self.orig_w, self.orig_h],
            "auto_min_rect": self.auto, "stride": self.stride, "pad_value": PAD_VALUE,
            "interpolation": "INTER_LINEAR",
        }


def letterbox(image: np.ndarray, new_shape, auto: bool = False, stride: int = 32,
              scaleup: bool = True) -> tuple:
    """Resize keeping aspect ratio and pad. Returns (image, LetterboxInfo).

    new_shape: int or (h, w).
    auto=True pads only up to the next multiple of ``stride`` (minimum rectangle),
    as Ultralytics does for PyTorch models.
    """
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)
    h0, w0 = image.shape[:2]
    r = min(new_shape[0] / h0, new_shape[1] / w0)
    if not scaleup:
        r = min(r, 1.0)
    new_unpad = (int(round(w0 * r)), int(round(h0 * r)))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    if auto:
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)
    dw /= 2
    dh /= 2
    if (w0, h0) != new_unpad:
        image = cv2.resize(image, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT,
                               value=(PAD_VALUE, PAD_VALUE, PAD_VALUE))
    info = LetterboxInfo(gain=r, pad_left=left, pad_top=top, out_w=image.shape[1],
                         out_h=image.shape[0], orig_w=w0, orig_h=h0, auto=auto, stride=stride)
    return image, info


def unletterbox_boxes(boxes_xyxy: np.ndarray, info: LetterboxInfo, clip: bool = True) -> np.ndarray:
    """Map boxes from letterboxed-input pixels back to original-image pixels."""
    b = np.asarray(boxes_xyxy, dtype=np.float64).copy()
    if b.size == 0:
        return b.reshape(0, 4)
    b[:, [0, 2]] -= info.pad_left
    b[:, [1, 3]] -= info.pad_top
    b /= info.gain
    if clip:
        b[:, [0, 2]] = b[:, [0, 2]].clip(0, info.orig_w)
        b[:, [1, 3]] = b[:, [1, 3]].clip(0, info.orig_h)
    return b


def letterbox_boxes(boxes_xyxy: np.ndarray, info: LetterboxInfo) -> np.ndarray:
    """Inverse of :func:`unletterbox_boxes` (original -> letterboxed input pixels)."""
    b = np.asarray(boxes_xyxy, dtype=np.float64).copy().reshape(-1, 4)
    b *= info.gain
    b[:, [0, 2]] += info.pad_left
    b[:, [1, 3]] += info.pad_top
    return b


def unletterbox_map(heat: np.ndarray, info: LetterboxInfo) -> np.ndarray:
    """Crop the padding off a map in letterbox space and resize to original size."""
    if heat.shape[:2] != (info.out_h, info.out_w):
        heat = cv2.resize(heat, (info.out_w, info.out_h), interpolation=cv2.INTER_LINEAR)
    uw = int(round(info.orig_w * info.gain))
    uh = int(round(info.orig_h * info.gain))
    crop = heat[info.pad_top:info.pad_top + uh, info.pad_left:info.pad_left + uw]
    return cv2.resize(crop, (info.orig_w, info.orig_h), interpolation=cv2.INTER_LINEAR)


def xywh2xyxy(b: np.ndarray) -> np.ndarray:
    b = np.asarray(b, dtype=np.float64)
    out = np.empty_like(b)
    out[..., 0] = b[..., 0] - b[..., 2] / 2
    out[..., 1] = b[..., 1] - b[..., 3] / 2
    out[..., 2] = b[..., 0] + b[..., 2] / 2
    out[..., 3] = b[..., 1] + b[..., 3] / 2
    return out


def box_iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU matrix between boxes a (N,4) and b (M,4), xyxy."""
    a = np.asarray(a, dtype=np.float64).reshape(-1, 4)
    b = np.asarray(b, dtype=np.float64).reshape(-1, 4)
    tl = np.maximum(a[:, None, :2], b[None, :, :2])
    br = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.prod(np.clip(br - tl, 0, None), axis=2)
    area_a = np.prod(np.clip(a[:, 2:] - a[:, :2], 0, None), axis=1)
    area_b = np.prod(np.clip(b[:, 2:] - b[:, :2], 0, None), axis=1)
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thres: float) -> np.ndarray:
    """Greedy NMS; returns kept indices sorted by descending score."""
    order = np.argsort(-scores, kind="stable")
    keep = []
    boxes = np.asarray(boxes, dtype=np.float64)
    while order.size:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        ious = box_iou(boxes[i:i + 1], boxes[order[1:]])[0]
        order = order[1:][ious <= iou_thres]
    return np.asarray(keep, dtype=np.int64)


def yolo_raw_postprocess(pred: np.ndarray, conf_thres: float, iou_thres: float,
                         max_det: int = 300, max_nms: int = 30000, max_wh: int = 7680):
    """Post-process a YOLOv8/YOLO11 raw head output of shape (4 + nc, A).

    Rows 0..3 are (cx, cy, w, h) in input pixels, rows 4.. are per-class scores
    (sigmoid already applied in Ultralytics exports). Mirrors Ultralytics
    ``non_max_suppression`` with multi_label=False, agnostic=False.
    Returns (boxes_xyxy (K,4), scores (K,), class_ids (K,), anchor_idx (K,)).
    """
    pred = np.asarray(pred, dtype=np.float32)
    nc = pred.shape[0] - 4
    if nc <= 0:
        raise ValueError("output has no class rows")
    cls_scores = pred[4:, :]
    conf = cls_scores.max(axis=0)
    cls = cls_scores.argmax(axis=0)
    mask = conf > conf_thres
    idx = np.nonzero(mask)[0]
    if idx.size == 0:
        z = np.zeros((0,), np.float32)
        return np.zeros((0, 4), np.float32), z, z.astype(np.int64), z.astype(np.int64)
    boxes = xywh2xyxy(pred[:4, idx].T)
    conf, cls = conf[idx], cls[idx]
    order = np.argsort(-conf, kind="stable")[:max_nms]
    boxes, conf, cls, idx = boxes[order], conf[order], cls[order], idx[order]
    keep = nms(boxes + cls[:, None] * max_wh, conf, iou_thres)[:max_det]
    return boxes[keep], conf[keep], cls[keep].astype(np.int64), idx[keep]


# ---------------------------------------------------------------- file I/O
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def imread_unicode(path: str) -> np.ndarray:
    """cv2.imread that works with Thai / non-ASCII paths on Windows."""
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"อ่านไฟล์ภาพไม่ได้: {os.path.basename(path)}")
    return img


def imwrite_unicode(path: str, image: np.ndarray, params=None) -> None:
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, image, params or [])
    if not ok:
        raise IOError(f"เข้ารหัสภาพไม่สำเร็จ: {path}")
    buf.tofile(path)


def list_images(folder: str) -> list:
    out = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(IMAGE_EXTS):
            out.append(os.path.join(folder, name))
    return out


# ---------------------------------------------------------------- colours / overlays
_PALETTE = [
    (0x3D, 0x7B, 0xF5), (0x9B, 0x4D, 0xE8), (0x2E, 0xB8, 0x5C), (0xF5, 0x8A, 0x2A),
    (0xE8, 0x3D, 0x5B), (0x1F, 0xB5, 0xC7), (0xC7, 0xA3, 0x1F), (0x7A, 0x5C, 0xFF),
    (0x00, 0x99, 0x88), (0xD9, 0x4F, 0xC6), (0x5C, 0x9E, 0x2E), (0xF2, 0x5C, 0x2A),
    (0x2A, 0x5C, 0xF2), (0xA6, 0x6B, 0x3D), (0x48, 0x48, 0xC8), (0x8E, 0xB8, 0x1F),
]


def class_color_rgb(class_id: int) -> tuple:
    return _PALETTE[int(class_id) % len(_PALETTE)]


def class_color_bgr(class_id: int) -> tuple:
    r, g, b = class_color_rgb(class_id)
    return (b, g, r)


def heatmap_to_color(heat01: np.ndarray) -> np.ndarray:
    """0..1 float map -> BGR uint8 JET colour map."""
    h = np.clip(heat01, 0, 1)
    return cv2.applyColorMap((h * 255).astype(np.uint8), cv2.COLORMAP_JET)


def overlay_heatmap(image_bgr: np.ndarray, heat01: np.ndarray, opacity: float) -> np.ndarray:
    color = heatmap_to_color(heat01)
    if color.shape[:2] != image_bgr.shape[:2]:
        color = cv2.resize(color, (image_bgr.shape[1], image_bgr.shape[0]))
    a = float(np.clip(opacity, 0, 1))
    return cv2.addWeighted(image_bgr, 1 - a, color, a, 0)


def draw_detections_basic(image_bgr: np.ndarray, detections, label_fn=None) -> np.ndarray:
    """Fallback renderer without Thai text support (used in headless/tests).

    The GUI uses a QPainter renderer so Thai labels are shaped correctly.
    """
    out = image_bgr.copy()
    for d in detections:
        x1, y1, x2, y2 = (int(round(v)) for v in d.box)
        c = class_color_bgr(d.class_id)
        cv2.rectangle(out, (x1, y1), (x2, y2), c, 2)
        text = label_fn(d) if label_fn else f"{d.class_id} {d.confidence:.2f}"
        text = text.encode("ascii", "replace").decode()
        cv2.putText(out, text, (x1 + 2, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1,
                    cv2.LINE_AA)
    return out


def side_by_side(left: np.ndarray, right: np.ndarray, gap: int = 8) -> np.ndarray:
    h = max(left.shape[0], right.shape[0])

    def pad(im):
        if im.shape[0] == h:
            return im
        return cv2.copyMakeBorder(im, 0, h - im.shape[0], 0, 0, cv2.BORDER_CONSTANT,
                                  value=(255, 255, 255))
    sep = np.full((h, gap, 3), 255, np.uint8)
    return np.hstack([pad(left), sep, pad(right)])
