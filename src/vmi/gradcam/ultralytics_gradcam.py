"""Grad-CAM for one *detection instance* of a YOLOv8 / YOLO11 PyTorch model.

How the post-NMS detection is mapped back to a pre-NMS target
-------------------------------------------------------------
1. The snapshot image is letterboxed exactly like the Ultralytics predictor
   does for PyTorch models (min-rect, stride multiple, pad 114).
2. One forward pass is run with autograd enabled (no ``no_grad`` /
   ``inference_mode``). The Detect head returns, before NMS, a tensor of shape
   (1, 4+nc, A): decoded boxes (cx, cy, w, h in input pixels) and per-class
   sigmoid scores for every anchor A.
3. The selected detection's box (original image pixels) is mapped into
   letterbox pixels and compared with every anchor box. NMS keeps the anchor
   with the highest score, and its box *is* the detection box, so the matching
   anchor is the one with IoU ≈ 1 and score ≈ reported confidence. We pick the
   anchor with the highest IoU among anchors whose class score for the
   detection's class is at least half the reported confidence. Match IoU and
   score difference are reported; no match -> error (no fake heat map).
4. Target scalar = that anchor's class score (still attached to the graph).
5. Gradients are taken w.r.t. the chosen feature map. "Auto" picks the head
   input (P3/P4/P5) whose grid contains the matched anchor.
6. Grad-CAM = ReLU(sum_k mean(dS/dA_k) * A_k), normalised, resized to the
   letterbox, padding removed, resized to the original image.
   Optional "HiResCAM" (Draelos & Carin 2020) = ReLU(sum_k dS/dA_k ⊙ A_k) keeps
   the gradient's spatial layout. Standard Grad-CAM averages the gradient over
   space, so it often lights up *every* object of the same class; HiResCAM is
   more faithful to the single selected instance.

A separate, *unfused* copy of the network is used because the predictor's
fused weights are created inside ``torch.inference_mode`` and cannot take
part in autograd. The copy is created lazily, placed on the GPU only when
enough free memory is reported, and released with the model.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from ..core.imageops import (box_iou, letterbox, letterbox_boxes, unletterbox_map, xywh2xyxy)
from ..core.types import Detection

log = logging.getLogger(__name__)


class GradCamError(RuntimeError):
    """User-facing Thai message; no heat map is produced."""


@dataclass
class GradCamOutput:
    heatmap: np.ndarray            # float32 (H, W) 0..1 in original image size
    layer_key: str
    layer_name: str
    details: dict = field(default_factory=dict)


def _extract_preds(out, nc: int):
    import torch
    cands = []
    if isinstance(out, torch.Tensor):
        cands = [out]
    elif isinstance(out, (list, tuple)):
        cands = [o for o in out if isinstance(o, torch.Tensor)]
    elif isinstance(out, dict):
        cands = [v for v in out.values() if isinstance(v, torch.Tensor)]
    for t in cands:
        if t.dim() == 3 and t.shape[1] == 4 + nc:
            return t
    shapes = [tuple(t.shape) for t in cands]
    raise GradCamError(f"ไม่รู้จักรูปแบบ output ของ head ก่อน NMS (พบ {shapes}) — ไม่สร้าง Heatmap")


class UltralyticsGradCAM:
    MIN_MATCH_IOU = 0.5

    def __init__(self, adapter):
        self.adapter = adapter
        self._net = None
        self._dev = "cpu"
        self.placement_note = ""

    # ------------------------------------------------------------ layers
    def _structure(self):
        net = self._net if self._net is not None else self.adapter.yolo.model
        return net, net.model[-1]

    def layer_options(self) -> list:
        net, head = self._structure()
        opts = [("auto", "อัตโนมัติ (แนะนำ)")]
        for lvl, i in enumerate(head.f):
            opts.append((f"layer:{i}", f"P{lvl + 3} • layer {i} ({type(net.model[i]).__name__})"))
        for i, m in enumerate(net.model):
            if type(m).__name__ == "SPPF":
                opts.append((f"layer:{i}", f"SPPF (backbone) • layer {i}"))
        return opts

    # ------------------------------------------------------------ model copy
    def _ensure_net(self):
        if self._net is not None:
            return
        import torch
        from ultralytics import YOLO
        fresh = YOLO(self.adapter.path).model.float().eval()
        for p in fresh.parameters():
            p.requires_grad_(False)
        dev = "cpu"
        note = ""
        if self.adapter.device.startswith("cuda") and torch.cuda.is_available():
            free, _total = torch.cuda.mem_get_info()
            param_bytes = sum(p.numel() * p.element_size() for p in fresh.parameters())
            need = param_bytes * 4 + 768 * 1024 * 1024
            if free > need:
                dev = self.adapter.device
            else:
                note = (f"หน่วยความจำ GPU ว่าง {free / 2**20:.0f} MB ไม่พอสำหรับสำเนาโมเดล Grad-CAM "
                        "จึงคำนวณ Grad-CAM บน CPU")
        self._net = fresh.to(dev)
        self._dev = dev
        self.placement_note = note
        log.info("Grad-CAM model copy on %s %s", dev, note)

    def release(self):
        self._net = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # ------------------------------------------------------------ main
    METHODS = (("gradcam", "Grad-CAM (มาตรฐาน)"), ("hirescam", "HiResCAM (ละเอียดรายวัตถุ)"))

    def compute(self, image_bgr: np.ndarray, det: Detection, imgsz: int,
                layer_key: str = "auto", method: str = "gradcam") -> GradCamOutput:
        import torch
        t0 = time.perf_counter()
        with self.adapter.lock:
            self._ensure_net()
            net = self._net
            head = net.model[-1]
            nc = int(head.nc)
            if not (0 <= int(det.class_id) < nc):
                raise GradCamError(f"รหัสคลาส {det.class_id} อยู่นอกช่วงของโมเดล (0..{nc - 1})")
            feat_idx = [int(i) for i in head.f]
            chosen = None
            if layer_key != "auto":
                try:
                    chosen = int(layer_key.split(":", 1)[1])
                    _ = net.model[chosen]
                except Exception:
                    raise GradCamError(f"ไม่พบชั้นเป้าหมาย '{layer_key}' ในโมเดลนี้") from None

            stride = self.adapter.info.caps.stride if self.adapter.info else 32
            s = self.adapter.valid_imgsz(imgsz)
            lb, info = letterbox(image_bgr, s, auto=True, stride=stride)
            x = torch.from_numpy(np.ascontiguousarray(lb[:, :, ::-1].transpose(2, 0, 1)))
            x = x.to(self._dev).float().div(255.0).unsqueeze(0).requires_grad_(True)

            acts = {}
            hooks = []

            def make_hook(idx):
                def hook(_m, _inp, out):
                    if isinstance(out, torch.Tensor):
                        if out.requires_grad:
                            out.retain_grad()
                        acts[idx] = out
                return hook

            for i in set(feat_idx) | ({chosen} if chosen is not None else set()):
                hooks.append(net.model[i].register_forward_hook(make_hook(i)))
            try:
                with torch.enable_grad():
                    out = net(x)
                    preds = _extract_preds(out, nc)
                    if not preds.requires_grad:
                        raise GradCamError("output ไม่เชื่อมกับ autograd — คำนวณ Grad-CAM ไม่ได้")
                    p0 = preds[0].detach().float().cpu().numpy()
                    boxes = xywh2xyxy(p0[:4].T)
                    cls_scores = p0[4 + int(det.class_id)]
                    target_box = letterbox_boxes([det.box], info)
                    ious = box_iou(target_box, boxes)[0]
                    ok = np.nonzero((ious >= self.MIN_MATCH_IOU) &
                                    (cls_scores >= 0.5 * float(det.confidence)))[0]
                    if ok.size == 0:
                        ok = np.nonzero(ious >= self.MIN_MATCH_IOU)[0]
                        if ok.size == 0:
                            raise GradCamError(
                                "ไม่พบ target ก่อน NMS ที่ตรงกับวัตถุที่เลือก (IoU < 0.5) — "
                                "อาจเปลี่ยนโมเดล/ขนาด input หลังจับภาพ ไม่สร้าง Heatmap")
                        a = int(ok[np.argmax(ious[ok] * cls_scores[ok])])
                    else:
                        a = int(ok[np.argmax(ious[ok] + 1e-3 * cls_scores[ok])])
                    target = preds[0, 4 + int(det.class_id), a]
                    net.zero_grad(set_to_none=True)
                    target.backward()

                counts = [int(acts[i].shape[2] * acts[i].shape[3]) for i in feat_idx]
                level = int(np.searchsorted(np.cumsum(counts), a, side="right"))
                level = min(level, len(feat_idx) - 1)
                layer = feat_idx[level] if chosen is None else chosen
                act = acts.get(layer)
                if act is None or act.grad is None:
                    raise GradCamError("ไม่ได้รับ gradient ที่ชั้นเป้าหมาย — ลองเลือกชั้นอื่น")
                A = act.detach()[0].float()
                G = act.grad.detach()[0].float()
                if not torch.isfinite(G).all() or float(G.abs().max()) == 0.0:
                    raise GradCamError("gradient เป็นศูนย์/ไม่ถูกต้องที่ชั้นนี้ — ไม่สร้าง Heatmap "
                                       "(ลองเลือกชั้นอื่น เช่น P3/P4/P5 ที่ตรงกับขนาดวัตถุ)")
                if method == "hirescam":
                    cam = torch.relu((G * A).sum(0))
                else:
                    w = G.mean(dim=(1, 2), keepdim=True)
                    cam = torch.relu((w * A).sum(0))
                cmax = float(cam.max())
                if not np.isfinite(cmax) or cmax <= 1e-12:
                    raise GradCamError("Grad-CAM ได้ค่าเป็นศูนย์ทั้งแผนที่ (ไม่มีบริเวณที่ส่งผลเชิงบวก) "
                                       "— ลองเลือกชั้นอื่น")
                cam = (cam / cmax).cpu().numpy().astype(np.float32)
                heat = unletterbox_map(cam, info)
                heat = np.clip(heat, 0, 1).astype(np.float32)
                score = float(cls_scores[a])
                details = {
                    "method": ("HiResCAM (Draelos & Carin 2020)" if method == "hirescam" else
                               "Grad-CAM (Selvaraju et al. 2017)") + " on pre-NMS class score",
                    "method_key": method,
                    "target_scalar": f"sigmoid class score, class {int(det.class_id)}, anchor {a}",
                    "matched_anchor_index": a,
                    "matched_level": f"P{level + 3}",
                    "match_iou": float(ious[a]),
                    "pre_nms_score": score,
                    "reported_confidence": float(det.confidence),
                    "score_difference": abs(score - float(det.confidence)),
                    "feature_map_shape": list(act.shape),
                    "letterbox": info.to_dict(),
                    "device": self._dev,
                    "elapsed_ms": (time.perf_counter() - t0) * 1000,
                }
                if ious[a] < 0.9 or abs(score - float(det.confidence)) > 0.05:
                    details["match_warning"] = ("การจับคู่ไม่ตรงพอดี (IoU/score ต่างจากผลตรวจ) "
                                                "โปรดตีความ Heatmap อย่างระมัดระวัง")
                if self.placement_note:
                    details["placement_note"] = self.placement_note
                name = f"layer {layer} ({type(net.model[layer]).__name__})"
                return GradCamOutput(heat, "auto" if chosen is None else layer_key, name, details)
            finally:
                for h in hooks:
                    h.remove()
                acts.clear()
                if x.grad is not None:
                    x.grad = None
                del x
                if self._dev.startswith("cuda"):
                    torch.cuda.empty_cache()
