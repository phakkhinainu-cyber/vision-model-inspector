"""End-to-end GUI tests (PySide6, real models, CPU). Uses a video file instead of a camera."""
import os
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("ultralytics")

from conftest import ASSETS_DIR, model_path  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(ASSETS_DIR, "demo.mp4")),
                                reason="test assets missing")


@pytest.fixture(scope="module")
def app():
    from vmi.app import create_app
    return create_app(["test"])


def wait_until(app, cond, timeout=60.0):
    from PySide6.QtCore import QEventLoop
    t = time.time()
    while time.time() - t < timeout:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture()
def win(app):
    from vmi.config import AppSettings
    from vmi.ui.main_window import MainWindow
    w = MainWindow(AppSettings())
    w.resize(1366, 768)
    w.show()
    yield w
    w.close()
    app.processEvents()


def load(app, w, name):
    done = []
    w.modelLoaded.connect(done.append)
    w.load_model(model_path(name), "cpu", confirm_trust=False)
    assert wait_until(app, lambda: bool(done), 120), "model did not load"
    assert done[0] is True
    return w.adapter


def test_full_flow_video_snapshot_gradcam_export(app, win, tmp_path):
    w = win
    assert not w.b_gradcam.isEnabled() and not w.b_capture.isEnabled()
    ad = load(app, w, "yolov8n.pt")
    assert ad.info.classes.count == 80
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("video"))
    w.set_file_source(os.path.join(ASSETS_DIR, "demo.mp4"))
    w.start_source()
    assert wait_until(app, lambda: w._live_pair is not None, 60), "no live inference result"
    pkt, res = w._live_pair
    assert res.frame_id == pkt.frame_id
    assert w.b_capture.isEnabled() and w.b_stop.isEnabled() and not w.b_start.isEnabled()
    n = []
    w.snapshotAdded.connect(n.append)
    for _ in range(3):
        w.capture_snapshot()
        assert wait_until(app, lambda k=len(n): len(n) > k, 60)
        wait_until(app, lambda: False, 0.3)
    assert len(w.store) == 3 and w.strip.count() == 3
    snap = w.current_snap
    assert snap is not None and snap.result.model.sha256 == ad.info.identity.sha256
    assert snap.result.detections, "demo video frame should contain detections"
    # Grad-CAM on selected detection
    assert w.b_gradcam.isEnabled()
    fin = []
    w.gradcamFinished.connect(fin.append)
    w.run_gradcam()
    assert w.worker.paused                       # live inference paused during Grad-CAM
    assert wait_until(app, lambda: bool(fin), 120)
    assert fin[0] is True and snap.gradcam is not None
    assert wait_until(app, lambda: not w.worker.paused, 5)
    assert w.gc_view.has_image()
    # export to a Thai folder name with spaces
    from vmi.core.export import ExportOptions
    out = tmp_path / "ผลลัพธ์ ทดสอบ"
    out.mkdir()
    files = w.export_snapshot_to(snap, str(out), ExportOptions())
    names = sorted(os.path.basename(f) for f in files)
    assert "gradcam_overlay.png" in names and "metadata.json" in names and "detections.csv" in names
    w.stop_source()
    assert wait_until(app, lambda: w.source is None, 10)
    # repeated start/stop must not hang
    for _ in range(3):
        w.start_source()
        wait_until(app, lambda: False, 0.4)
        w.stop_source()
    assert w.source is None


def test_model_switch_keeps_old_snapshots(app, win):
    w = win
    load(app, w, "yolov8n.pt")
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("image"))
    w.set_file_source(os.path.join(ASSETS_DIR, "images", "bus.jpg"))
    w.start_source()
    assert wait_until(app, lambda: w._live_pair is not None, 60)
    n = []
    w.snapshotAdded.connect(n.append)
    w.capture_snapshot()
    assert wait_until(app, lambda: bool(n), 30)
    old = w.current_snap
    old_names = dict(old.class_names)
    load(app, w, "custom3_untrained.pt")
    assert w.class_view.registry.count == 3
    assert old.class_names == old_names            # not relabelled
    w.strip.select_index(old.index)
    assert not w.b_gradcam.isEnabled()             # snapshot from another model
    load(app, w, "yolov8n.onnx")
    assert w.adapter.info.identity.file_format == ".onnx"
    assert not w.layer_combo.isEnabled()           # Grad-CAM disabled for ONNX
    assert not w.imgsz_combo.isEnabled()           # static ONNX input


def test_class_filter_hides_rows(app, win):
    w = win
    ad = load(app, w, "yolov8n.pt")
    h = ad.info.identity.sha256
    person = [k for k, v in ad.info.classes.names.items() if v == "person"][0]
    w.names_store.set_display_names(h, {person: "คน"})
    w.names_store.set_hidden(h, set())
    w._apply_class_view()
    w.mode_combo.setCurrentIndex(w.mode_combo.findData("image"))
    w.set_file_source(os.path.join(ASSETS_DIR, "images", "bus.jpg"))
    w.start_source()
    assert wait_until(app, lambda: w._live_pair is not None, 60)
    n = []
    w.snapshotAdded.connect(n.append)
    w.capture_snapshot()
    assert wait_until(app, lambda: bool(n), 30)
    rows_all = w.table.rowCount()
    labels = {w.table.item(r, 2).text() for r in range(rows_all)}
    assert "คน" in labels
    for s in w.store.all():
        s.hidden_classes = {person}
    w._show_snapshot()
    assert w.table.rowCount() < rows_all
    w.names_store.set_display_names(h, {})


def test_layout_small_screen(app, win):
    w = win
    w.resize(1366, 768)
    app.processEvents()
    assert w.width() <= 1366 and w.height() <= 768
    assert w.minimumSizeHint().width() <= 1366
