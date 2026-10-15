"""Drive the real application and save screenshots for the manual.

Usage: python tools/screenshots.py <out_dir>
Requires test_assets (tools/make_test_assets.py). Everything shown is produced
by the real models running on CPU; nothing is mocked.
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
ASSETS = os.path.join(ROOT, "test_assets")
MODELS = os.path.join(ASSETS, "models")


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    os.environ.setdefault("VMI_DATA_DIR", os.path.join(out_dir, "_appdata"))
    from PySide6.QtCore import QEventLoop
    from vmi.app import create_app
    from vmi.config import AppSettings
    from vmi.ui.main_window import MainWindow
    from vmi.ui.icons import icon

    app = create_app(["shots"])
    log = {}

    def pump(sec):
        t = time.time()
        while time.time() - t < sec:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
            time.sleep(0.01)

    def wait(cond, timeout=120):
        t = time.time()
        while time.time() - t < timeout:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
            if cond():
                return True
            time.sleep(0.01)
        raise RuntimeError("timeout")

    def shot(widget, name):
        pump(0.4)
        p = os.path.join(out_dir, name)
        widget.grab().save(p)
        print("saved", p)

    w = MainWindow(AppSettings())
    w.setWindowIcon(icon("eye", "#5B3FD9", 64))
    w.resize(1600, 1000)
    w.show()
    pump(0.5)
    shot(w, "00_start.png")

    done = []
    w.modelLoaded.connect(done.append)
    w.load_model(os.path.join(MODELS, "yolov8n.pt"), "cpu", confirm_trust=False)
    wait(lambda: done)
    ad = w.adapter
    names = ad.info.classes.names
    thai = {"person": "คน", "bus": "รถบัส", "car": "รถยนต์", "handbag": "กระเป๋าถือ",
            "backpack": "เป้", "tie": "เนกไท", "stop sign": "ป้ายหยุด"}
    w.names_store.set_display_names(ad.info.identity.sha256,
                                    {k: thai[v] for k, v in names.items() if v in thai})
    w._apply_class_view()

    w.mode_combo.setCurrentIndex(w.mode_combo.findData("video"))
    w.set_file_source(os.path.join(ASSETS, "demo.avi"))
    w.start_source()
    wait(lambda: w._live_pair is not None)
    snaps = []
    w.snapshotAdded.connect(snaps.append)
    for i in range(6):
        pump(0.55)
        k = len(snaps)
        w.capture_snapshot()
        wait(lambda: len(snaps) > k)
    # pick snapshot with most people
    best = max(w.store.all(), key=lambda s: sum(1 for d in s.result.detections
                                                if names[d.class_id] == "person"))
    w.strip.select_index(best.index)
    pump(0.3)
    people = [d for d in best.result.detections if names[d.class_id] == "person"]
    target = max(people or best.result.detections, key=lambda d: d.confidence)
    w.select_detection(target.det_id)
    fin = []
    w.gradcamFinished.connect(fin.append)
    w.run_gradcam()
    pump(0.15)
    shot(w, "02_gradcam_running.png")
    wait(lambda: fin)
    pump(1.2)
    shot(w, "01_main.png")
    log["gradcam"] = {k: v for k, v in best.gradcam.details.items() if k != "letterbox"} if best.gradcam else None

    # 1366x768
    w.resize(1366, 768)
    pump(0.8)
    shot(w, "07_main_1366x768.png")
    w.resize(1600, 1000)
    pump(0.5)

    # class manager
    from vmi.ui.dialogs.class_manager import ClassManagerDialog
    cv = w.class_view
    dlg = ClassManagerDialog(cv.registry, cv.display, cv.hidden, ad.output_class_count(), ad.info.identity.name, w)
    dlg.show()
    shot(dlg, "03_class_manager.png")
    dlg.close()

    from vmi.ui.dialogs.model_info import ModelInfoDialog
    dlg = ModelInfoDialog(ad.info, w)
    dlg.show()
    shot(dlg, "04_model_info.png")
    dlg.close()

    from vmi.ui.dialogs.camera_dialog import CameraDialog
    w.stop_source()
    dlg = CameraDialog(w.settings, None, w)
    dlg.show()
    shot(dlg, "05_camera_dialog.png")
    dlg.tabs.setCurrentIndex(2)
    dlg.ip_name.setText("กล้องหน้าโรงงาน")
    dlg.ip_url.setText("rtsp://192.168.1.64:554/Streaming/Channels/101")
    dlg.ip_user.setText("viewer")
    shot(dlg, "05b_camera_rtsp.png")
    dlg.tabs.setCurrentIndex(1)
    shot(dlg, "05c_camera_manual.png")
    dlg.close()

    from vmi.ui.dialogs.export_dialog import ExportDialog
    dlg = ExportDialog(os.path.join(out_dir, "export"), True, False, w)
    dlg.show()
    shot(dlg, "06_export_dialog.png")
    dlg.close()

    # real export of the analysed snapshot (Thai folder)
    from vmi.core.export import ExportOptions
    exp = os.path.join(out_dir, "ตัวอย่างการส่งออก")
    os.makedirs(exp, exist_ok=True)
    files = w.export_snapshot_to(best, exp, ExportOptions())
    log["export_files"] = [os.path.relpath(f, out_dir) for f in files]

    # ONNX model: Grad-CAM disabled
    done.clear()
    w.load_model(os.path.join(MODELS, "yolov8n.onnx"), "cpu", confirm_trust=False)
    wait(lambda: done)
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("image"))
    w.set_file_source(os.path.join(ASSETS, "images", "zidane.jpg"))
    w.start_source()
    wait(lambda: w._live_pair is not None)
    k = len(snaps)
    w.capture_snapshot()
    wait(lambda: len(snaps) > k)
    pump(0.8)
    shot(w, "08_onnx_model.png")
    log["onnx_detections"] = len(w.current_snap.result.detections)

    with open(os.path.join(out_dir, "screenshots_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2, default=str)
    w.close()
    pump(0.3)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
