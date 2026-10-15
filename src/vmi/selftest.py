"""Non-interactive self test, used to verify a frozen / installed build.

VisionModelInspector.exe --selftest --model M.pt --image I.jpg --out result.json [--screenshot S.png]

Loads the model through the normal adapter registry, runs detection and (if
supported) Grad-CAM for the most confident detection, optionally builds the
main window off-screen and saves a screenshot. Writes a JSON report and exits
with 0 on success, 1 on failure. Never needs network access.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback


def run(argv) -> int:
    ap = argparse.ArgumentParser(prog="VisionModelInspector --selftest")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--model", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--screenshot", default="")
    a = ap.parse_args(argv)
    rep = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)), "executable": sys.executable}
    t0 = time.time()
    try:
        from . import __version__
        from .adapters.registry import create_adapter
        from .core.imageops import imread_unicode
        from .core.sysinfo import dependency_versions
        from .core.types import InferenceSettings
        rep["version"] = __version__
        rep["dependencies"] = dependency_versions()
        ad = create_adapter(a.model)
        info = ad.load(a.model, "cpu")
        rep["model"] = info.identity.to_dict()
        rep["classes"] = info.classes.count
        img = imread_unicode(a.image)
        s = InferenceSettings(device="cpu")
        t = time.time()
        dets = ad.predict(img, s)
        rep["inference_ms_first"] = (time.time() - t) * 1000
        t = time.time()
        dets = ad.predict(img, s)
        rep["inference_ms_second"] = (time.time() - t) * 1000
        rep["detections"] = [dict(d.to_dict(), name=info.classes.name(d.class_id)) for d in dets]
        eng = ad.gradcam_engine()
        if eng is not None and dets:
            d = max(dets, key=lambda x: x.confidence)
            t = time.time()
            out = eng.compute(img, d, s.imgsz)
            rep["gradcam"] = {"ok": True, "ms": (time.time() - t) * 1000, "layer": out.layer_name,
                              "match_iou": out.details["match_iou"],
                              "score_difference": out.details["score_difference"]}
        else:
            rep["gradcam"] = {"ok": False, "reason": info.gradcam_status}
        if a.screenshot:
            from .app import create_app
            from .config import AppSettings
            from .ui.main_window import MainWindow
            app = create_app(["selftest"])
            from .ui import theme
            rep["ui_font"] = getattr(theme, "FONT_FAMILY_ACTIVE", "")
            w = MainWindow(AppSettings())
            w.resize(1366, 768)
            w.show()
            for _ in range(20):
                app.processEvents()
                time.sleep(0.02)
            w.grab().save(a.screenshot)
            rep["screenshot"] = a.screenshot
            w.close()
            app.processEvents()
        ad.close()
        rep["ok"] = len(dets) > 0
    except Exception as e:
        rep["error"] = f"{type(e).__name__}: {e}"
        rep["traceback"] = traceback.format_exc()
    rep["elapsed_s"] = time.time() - t0
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2, default=str)
    return 0 if rep["ok"] else 1
