"""ทดสอบตัวเองหลังติดตั้ง: โหลดโมเดล, ประมวลผลวิดีโอตัวอย่าง, บันทึกลงฐานข้อมูล, เปิด web server แล้วเรียก API"""
from __future__ import annotations

import json
import platform
import socket
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__
from .config import MODEL_FILES, app_dir, find_model, frontend_dist


def demo_video() -> Path | None:
    for p in (app_dir() / "demo" / "demo.mp4",):
        if p.exists():
            return p
    return None


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_selftest(out: Path, video: Path | None = None, home: Path | None = None) -> int:
    res: dict[str, Any] = {"version": __version__, "python": sys.version.split()[0], "platform": platform.platform(),
                           "frozen": bool(getattr(sys, "frozen", False)), "ok": False, "steps": {}}
    home = home or Path(tempfile.mkdtemp(prefix="lpr-selftest-"))
    try:
        from .camera.pipeline import CameraPipeline, Models
        from .config import Paths
        from .context import AppContext
        from .settings import DEFS
        from .vision.runtime import available_providers, gpu_adapters, probe

        paths = Paths(home).ensure()
        res["providers"] = available_providers()
        res["gpu_adapters"] = list(gpu_adapters())
        res["models"] = {k: str(find_model(paths, k)) if find_model(paths, k) else None for k in MODEL_FILES}
        res["frontend"] = (frontend_dist() / "index.html").exists()
        try:
            import webview  # noqa: F401

            res["webview"] = True
        except Exception as e:  # noqa: BLE001
            res["webview"] = f"ไม่มี ({type(e).__name__}) จะเปิดผ่านเบราว์เซอร์แทน"
        ctx = AppContext(home, start_cameras=False)
        params = {d.key: d.default for d in DEFS}
        t0 = time.time()
        models = Models({k: v for k, v in res["models"].items()}, params)
        res["steps"]["load_models_s"] = round(time.time() - t0, 2)
        res["model_info"] = models.info()
        gpu_eps = {"CUDAExecutionProvider", "DmlExecutionProvider"} & set(res["providers"])
        if gpu_eps and find_model(paths, "vehicle"):
            vm = find_model(paths, "vehicle")
            res["gpu_probe"] = {d: probe(vm, d) for d in ("cpu", "auto", "dml" if "DmlExecutionProvider" in
                                                            res["providers"] else "cuda")}
        video = video or demo_video()
        events = []
        if video is not None and video.exists():
            import cv2

            pipe = CameraPipeline({"id": None, "role": "สองทาง", "roi_polygon": [],
                                   "line_coords": [[0.05, 0.6], [0.95, 0.6]], "line_direction": "pos_in"},
                                  params, models)
            cap = cv2.VideoCapture(str(video))
            fps = cap.get(cv2.CAP_PROP_FPS) or 15
            i, t1 = 0, time.time()
            size = (0, 0)
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                size = (frame.shape[1], frame.shape[0])
                for ev in pipe.step(frame, frame, 1_700_000_000 + i / fps):
                    if ev["type"] == "event_revise":
                        ctx.events.revise(ev)
                        continue
                    e = ctx.events.ingest(ev)
                    if e:
                        events.append(e)
                i += 1
            for ev in pipe.flush(size):
                e = ctx.events.ingest(ev)
                if e:
                    events.append(e)
            res["steps"]["video_frames"] = i
            res["steps"]["video_s"] = round(time.time() - t1, 2)
            res["events"] = [{"plate": e["plate_display"], "province": e["province"], "direction": e["direction"],
                              "type": e["vehicle_type"], "conf": e["ocr_confidence"], "review": e["review_status"]}
                             for e in events]
            truth = video.with_suffix(".json")
            if truth.exists():
                t = json.loads(truth.read_text("utf-8"))
                res["accuracy"] = {"cars": len(t), "plate_ok": sum(1 for x in t if any(
                    e["plate_norm"] == x["plate_norm"] for e in events))}
        # web server + API
        import threading

        import uvicorn

        from .api.app import create_app

        port = _free_port()
        srv = uvicorn.Server(uvicorn.Config(create_app(ctx, manage_lifecycle=False), host="127.0.0.1", port=port,
                                            log_config=None))
        th = threading.Thread(target=srv.run, daemon=True)
        th.start()
        for _ in range(100):
            if srv.started:
                break
            time.sleep(0.1)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as r:
            res["steps"]["api_health"] = json.loads(r.read())
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            res["steps"]["index_bytes"] = len(r.read())
        srv.should_exit = True
        th.join(timeout=5)
        ctx.stop()
        need = ["vehicle", "ocr_rec", "ocr_dict"]
        res["ok"] = all(res["models"].get(k) for k in need) and (video is None or len(events) > 0)
        if "accuracy" in res:
            res["ok"] = res["ok"] and res["accuracy"]["plate_ok"] >= max(1, res["accuracy"]["cars"] - 2)
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
        res["traceback"] = traceback.format_exc()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    return 0 if res["ok"] else 1
