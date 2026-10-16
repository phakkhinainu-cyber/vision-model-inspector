"""รันขั้นตอนประมวลผลของกล้องกับไฟล์วิดีโอแบบออฟไลน์ (เร็วกว่าเวลาจริง) แล้วเทียบกับเฉลย (ถ้ามี)

python tools/eval_video.py work/demo/demo.mp4 [--truth work/demo/demo.json] [--line 0.05,0.6,0.95,0.6]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lpr import constants as C  # noqa: E402
from lpr.camera.pipeline import CameraPipeline, Models  # noqa: E402
from lpr.settings import DEFS  # noqa: E402


def model_paths(models_dir: Path) -> dict[str, str | None]:
    from lpr.config import MODEL_FILES

    return {k: (str(models_dir / v) if (models_dir / v).exists() else None) for k, v in MODEL_FILES.items()}


def run(video: Path, models_dir: Path, line: list[list[float]], role: str = C.ROLE_BOTH,
        params_override: dict | None = None) -> tuple[list[dict], dict]:
    params = {d.key: d.default for d in DEFS}
    params.update(params_override or {})
    models = Models(model_paths(models_dir), params)
    cam = {"id": 1, "name": "test", "role": role, "roi_polygon": [], "line_coords": line,
           "line_direction": C.LINE_POS_IN}
    pipe = CameraPipeline(cam, params, models)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    events = []
    i = 0
    t0 = time.time()
    size = (0, 0)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        size = (frame.shape[1], frame.shape[0])
        ts = 1_000_000.0 + i / fps
        for ev in pipe.step(frame, frame, ts):
            ev["t"] = round(ts - 1_000_000.0, 2)
            if ev["type"] == "event_revise":
                for e in events:
                    if e["uid"] == ev["uid"]:
                        e.update({k: v for k, v in ev.items() if k not in ("type", "t", "ts", "direction")},
                                 revised=True)
                continue
            # จำลองการกันบันทึกซ้ำ (ป้ายเดียวกันภายใน dedup_seconds)
            if any(e["plate_norm"] and e["plate_norm"] == ev["plate_norm"] and
                   ev["ts"] - e["ts"] < params["dedup_seconds"] for e in events):
                continue
            events.append(ev)
        i += 1
    for ev in pipe.flush(size):
        ev["t"] = round(i / fps, 2)
        events.append(ev)
    stats = dict(pipe.stats, frames=i, seconds=round(time.time() - t0, 1), video_seconds=round(i / fps, 1),
                 **models.info())
    return events, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--truth", default="")
    ap.add_argument("--models", default=str(ROOT / "models"))
    ap.add_argument("--line", default="0.05,0.6,0.95,0.6")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    v = [float(x) for x in a.line.split(",")] if a.line else []
    line = [[v[0], v[1]], [v[2], v[3]]] if len(v) == 4 else []
    events, stats = run(Path(a.video), Path(a.models), line)
    print(json.dumps(stats, ensure_ascii=False))
    for e in events:
        print(f"t={e['t']:6.2f} {e['direction']} {e['plate_display'] or '(อ่านไม่ได้)':>10} {e['province']:<16} "
              f"conf={e['confidence']:.2f} type={e['vehicle_type']} color={e['plate_bg']}/{e['plate_fg']} "
              f"frames={e['frames']}{' (แก้ไขภายหลัง)' if e.get('revised') else ''}")
    result = {"stats": stats, "events": [{k: v for k, v in e.items() if not k.endswith("_jpg")} for e in events]}
    if a.truth:
        truth = json.loads(Path(a.truth).read_text("utf-8"))
        ok_plate = sum(1 for t in truth if any(e["plate_norm"] == t["plate_norm"] for e in events))
        ok_prov = sum(1 for t in truth if any(e["plate_norm"] == t["plate_norm"] and e["province"] == t["province"]
                                              for e in events))
        result["accuracy"] = {"cars": len(truth), "events": len(events), "plate_ok": ok_plate, "province_ok": ok_prov}
        print("ACCURACY", json.dumps(result["accuracy"]))
    if a.out:
        Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
