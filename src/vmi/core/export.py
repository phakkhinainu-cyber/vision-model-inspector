"""Export a snapshot (images, CSV, JSON metadata) to a user-chosen folder.

* never overwrites: a new unique folder / file name is generated if needed
* supports Thai characters and spaces in paths (np.tofile / utf-8)
* nothing is sent anywhere — files are written locally only
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import re
from dataclasses import dataclass

from .. import __version__, APP_NAME
from .imageops import (draw_detections_basic, imwrite_unicode, overlay_heatmap,
                       heatmap_to_color, side_by_side)
from .snapshots import Snapshot
from .sysinfo import dependency_versions
from .types import format_confidence

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str, max_len: int = 80) -> str:
    name = _ILLEGAL.sub("_", name).strip().rstrip(".")
    return (name or "export")[:max_len]


def unique_path(path: str) -> str:
    """Return ``path`` or ``path (2)``, ``path (3)``… that does not exist yet."""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    if os.path.isdir(path):
        root, ext = path, ""
    i = 2
    while True:
        cand = f"{root} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


@dataclass
class ExportOptions:
    original: bool = True
    annotated: bool = True
    heatmap: bool = True
    overlay: bool = True
    comparison: bool = True
    csv: bool = True
    json: bool = True
    only_visible: bool = False     # apply the class display filter to CSV/annotated
    heatmap_opacity: float = 0.5


def export_snapshot(snap: Snapshot, out_dir: str, opts: ExportOptions, render_fn=None,
                    extra_meta: dict | None = None, folder_name: str | None = None) -> list:
    """Write the selected outputs. ``render_fn(image, detections, label_fn) -> BGR``
    draws detection boxes (the GUI passes a Qt renderer with Thai text support).
    Returns the list of written file paths.
    """
    if not os.path.isdir(out_dir):
        raise FileNotFoundError(f"ไม่พบโฟลเดอร์ปลายทาง: {out_dir}")
    ts = _dt.datetime.fromtimestamp(snap.result.timestamp)
    model_stem = os.path.splitext(snap.result.model.name)[0]
    folder = folder_name or f"ภาพ{snap.index:02d}_{ts:%Y%m%d-%H%M%S}_{model_stem}"
    target = unique_path(os.path.join(out_dir, safe_name(folder)))
    os.makedirs(target)

    dets = snap.visible_detections() if opts.only_visible else list(snap.result.detections)
    label_fn = lambda d: f"{snap.label(d.class_id)} {format_confidence(d.confidence)}"  # noqa: E731
    render = render_fn or draw_detections_basic
    written = []

    def w_img(name, img):
        p = unique_path(os.path.join(target, name))
        imwrite_unicode(p, img)
        written.append(p)

    annotated = None
    if opts.original:
        w_img("original.png", snap.image)
    if opts.annotated or opts.comparison:
        annotated = render(snap.image, dets, label_fn)
        if opts.annotated:
            w_img("detections.png", annotated)
    gc = snap.gradcam
    if gc is not None:
        overlay = overlay_heatmap(snap.image, gc.heatmap, opts.heatmap_opacity)
        if opts.heatmap:
            w_img("gradcam_heatmap.png", heatmap_to_color(gc.heatmap))
        if opts.overlay:
            w_img("gradcam_overlay.png", overlay)
        if opts.comparison:
            w_img("comparison.png", side_by_side(annotated, overlay))
    elif opts.comparison and annotated is not None:
        w_img("comparison.png", side_by_side(annotated, snap.image))

    if opts.csv:
        p = unique_path(os.path.join(target, "detections.csv"))
        with open(p, "w", newline="", encoding="utf-8-sig") as f:   # BOM so Excel shows Thai
            wr = csv.writer(f)
            wr.writerow(["snapshot", "frame_id", "det_id", "class_id", "class_name",
                         "display_name", "confidence", "x1", "y1", "x2", "y2", "x", "y", "w", "h"])
            for d in dets:
                x, y, w, h = d.xywh
                wr.writerow([snap.index, snap.result.frame_id, d.det_id, d.class_id,
                             snap.class_names.get(int(d.class_id), ""),
                             snap.display_names.get(int(d.class_id), ""),
                             format_confidence(d.confidence),
                             *(f"{v:.1f}" for v in d.box), *(f"{v:.1f}" for v in (x, y, w, h))])
        written.append(p)

    if opts.json:
        meta = build_metadata(snap, opts, extra_meta)
        p = unique_path(os.path.join(target, "metadata.json"))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2, default=_json_default)
        written.append(p)
    return written


def build_metadata(snap: Snapshot, opts: ExportOptions, extra: dict | None) -> dict:
    r = snap.result
    meta = {
        "app": {"name": APP_NAME, "version": __version__},
        "exported_at": _dt.datetime.now().astimezone().isoformat(),
        "snapshot": {
            "index": snap.index, "frame_id": r.frame_id,
            "timestamp": _dt.datetime.fromtimestamp(r.timestamp).astimezone().isoformat(),
            "source": snap.source_label, "image_size": list(r.image_size),
        },
        "model": r.model.to_dict(),
        "device": r.device,
        "inference": {"settings": r.settings.to_dict(), "inference_ms": r.inference_ms},
        "class_mapping": {
            "source": snap.class_source,
            "classes": [{"class_id": k, "original_name": v,
                         "display_name": snap.display_names.get(k, ""),
                         "visible": k not in snap.hidden_classes}
                        for k, v in sorted(snap.class_names.items())],
        },
        "display_filter_applied_to_export": opts.only_visible,
        "detections": [dict(d.to_dict(), class_name=snap.class_names.get(int(d.class_id), ""))
                       for d in r.detections],
        "dependencies": dependency_versions(),
        "note": "ค่าความมั่นใจคือ score ของโมเดล ไม่ใช่ค่าความแม่นยำ (accuracy) ที่ประเมินจากชุดข้อมูลจริง",
    }
    if snap.gradcam is not None:
        g = snap.gradcam
        meta["gradcam"] = {
            "target": {"det_id": g.det_id, "class_id": g.class_id, "confidence": g.confidence,
                       "box_xyxy": list(map(float, g.box))},
            "layer_key": g.layer_key, "layer": g.layer_name,
            "overlay_opacity": opts.heatmap_opacity, "colormap": "JET",
            **g.details,
            "disclaimer": "Grad-CAM วิเคราะห์ภาพที่เลือก ไม่ใช่ภาพสด และแผนที่สีไม่ใช่ค่าความแม่นยำ",
        }
    if extra:
        meta.update(extra)
    return meta


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    if isinstance(o, set):
        return sorted(o)
    return str(o)
