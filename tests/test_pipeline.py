"""Capture / inference pipeline tests with a fake adapter and a generated video.

These do not need a real camera. Real-camera behaviour is reported separately
in docs/TEST_REPORT_TH.md.
"""
import threading
import time
import tracemalloc

import cv2
import numpy as np

from vmi.adapters.base import ModelAdapter, ModelInfo
from vmi.core.classes import ClassRegistry
from vmi.core.types import AdapterCapabilities, Detection, FramePacket, ModelIdentity
from vmi.pipeline.inference_worker import InferenceWorker, LatestFrameSlot
from vmi.sources.image_source import ImageSource
from vmi.sources.opencv_source import OpenCVSource


class FakeAdapter(ModelAdapter):
    """Encodes the frame number in pixel (0,0) and returns it as a box x1."""
    key = "fake"

    def __init__(self, delay=0.03):
        super().__init__()
        self.delay = delay
        self.calls = 0
        self.info = ModelInfo(ModelIdentity("fake", "/fake", "0" * 64, "fake", ".x"),
                              AdapterCapabilities("detect", (".x",), False), ClassRegistry({0: "a"}, "model"),
                              "cpu", True, "-")

    def load(self, path, device="auto"):
        return self.info

    def predict(self, image, settings):
        with self.lock:
            self.calls += 1
            time.sleep(self.delay)
            marker = int(image[0, 0, 0]) + 256 * int(image[0, 0, 1])
            return [Detection(0, 0, 0.9, (marker, 0, marker + 1, 1))]


def make_video(path, n=60, w=160, h=120, fps=60):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    assert vw.isOpened()
    for i in range(n):
        f = np.full((h, w, 3), 40, np.uint8)
        cv2.putText(f, str(i), (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        vw.write(f)
    vw.release()


def _pkt(i):
    img = np.zeros((8, 8, 3), np.uint8)
    img[0, 0, 0], img[0, 0, 1] = i % 256, i // 256
    return FramePacket.make(i, img)


def test_latest_frame_slot_is_bounded():
    s = LatestFrameSlot()
    for i in range(1000):
        s.put(_pkt(i))
        assert len(s) <= 1
    assert s.take().frame_id == 999 and s.dropped == 999 and s.take() is None


def test_results_match_their_frame():
    """Each result must describe exactly the frame it is delivered with."""
    ad = FakeAdapter(delay=0.02)
    got, errors = [], []
    w = InferenceWorker(on_result=lambda p, r, k, t: got.append((p, r, k)), on_error=errors.append)
    w.set_adapter(ad)
    w.start()
    for i in range(1, 300):
        w.submit_frame(_pkt(i))
        time.sleep(0.001)
    time.sleep(0.3)
    w.stop()
    assert not errors and len(got) > 5
    assert len(got) < 299                        # frames were dropped, not queued
    last = 0
    for pkt, res, kind in got:
        assert res.frame_id == pkt.frame_id
        assert int(res.detections[0].box[0]) == pkt.frame_id   # boxes computed on this frame
        assert pkt.frame_id > last                             # never an older frame afterwards
        last = pkt.frame_id


def test_jobs_have_priority_and_pause():
    ad = FakeAdapter(delay=0.01)
    got = []
    w = InferenceWorker(on_result=lambda p, r, k, t: got.append((k, t, r.frame_id)))
    w.set_adapter(ad)
    w.start()
    w.pause("gradcam")
    for i in range(50):
        w.submit_frame(_pkt(i))
    w.submit_job(_pkt(7), tag="snap-7")
    time.sleep(0.3)
    assert [g for g in got if g[0] == "live"] == []           # paused: no live inference
    assert ("job", "snap-7", 7) in got                        # snapshot jobs still run
    w.resume()
    w.submit_frame(_pkt(60))
    time.sleep(0.2)
    w.stop()
    assert any(g[0] == "live" and g[2] == 60 for g in got)


def test_rate_limit_every_n():
    ad = FakeAdapter(delay=0.0)
    got = []
    w = InferenceWorker(on_result=lambda p, r, k, t: got.append(r.frame_id))
    w.set_adapter(ad)
    w.set_rate(every_n=5, max_fps=0)
    w.start()
    for i in range(1, 101):
        w.submit_frame(_pkt(i))
        time.sleep(0.003)
    time.sleep(0.2)
    w.stop()
    assert 10 <= len(got) <= 20


def test_model_swap_waits_for_running_inference():
    a1, a2 = FakeAdapter(delay=0.2), FakeAdapter(delay=0.0)
    got = []
    w = InferenceWorker(on_result=lambda p, r, k, t: got.append(r))
    w.set_adapter(a1)
    w.start()
    w.submit_job(_pkt(1))
    time.sleep(0.05)                       # a1 is now busy
    t0 = time.perf_counter()
    w.set_adapter(a2)                      # must block until a1 finished
    assert time.perf_counter() - t0 >= 0.1
    w.submit_job(_pkt(2))
    time.sleep(0.1)
    w.stop()
    assert got[0].model.name == "fake" and len(got) == 2


def test_video_source_and_repeated_start_stop(tmp_path):
    path = str(tmp_path / "วิดีโอ ทดสอบ.avi")
    make_video(path, n=90)
    frames = []
    stopped = threading.Event()
    for round_ in range(5):
        stopped.clear()
        src = OpenCVSource("video", path, "test.avi")
        src.on_frame = frames.append
        src.on_stopped = stopped.set
        src.start()
        time.sleep(0.15)
        src.stop()
        assert stopped.wait(3), f"source did not stop (round {round_})"
        assert not src.running
    assert len(frames) > 10
    ids = [f.frame_id for f in frames[:5]]
    assert ids == sorted(ids)


def test_video_eof_and_pause(tmp_path):
    path = str(tmp_path / "v.avi")
    make_video(path, n=20, fps=200)
    frames, done = [], threading.Event()
    src = OpenCVSource("video", path, "v")
    src.on_frame = frames.append
    src.on_stopped = done.set
    src.start()
    assert done.wait(5)
    assert len(frames) == 20 and src.actual_resolution == (160, 120)


def test_bad_sources_report_errors(tmp_path):
    errs, done = [], threading.Event()
    src = OpenCVSource("video", str(tmp_path / "missing.mp4"), "x")
    src.on_error = errs.append
    src.start()
    assert errs and "ไม่พบไฟล์" in errs[0]
    errs.clear()
    src = OpenCVSource("opencv-index", 97, "cam97", open_timeout=2, reconnects=0)
    src.on_error, src.on_stopped = errs.append, done.set
    src.start()
    assert done.wait(10) and errs
    errs.clear(); done.clear()
    src = OpenCVSource("rtsp", "rtsp://127.0.0.1:9/none", "ipcam", open_timeout=1, reconnects=1)
    src.on_error, src.on_stopped = errs.append, done.set
    src.start()
    assert done.wait(20) and errs


def test_image_folder_source(tmp_path):
    for i in range(3):
        cv2.imwrite(str(tmp_path / f"{i}.png"), np.full((10, 10 + i, 3), i, np.uint8))
    (tmp_path / "note.txt").write_text("x")
    src = ImageSource.from_path(str(tmp_path))
    got = []
    src.on_frame = got.append
    src.start()
    src.step(1)
    src.step(1)
    src.step(1)
    assert [g.image.shape[1] for g in got] == [10, 11, 12, 10]


def test_memory_is_bounded_during_long_run():
    ad = FakeAdapter(delay=0.001)
    w = InferenceWorker(on_result=lambda *a: None)
    w.set_adapter(ad)
    w.start()
    tracemalloc.start()
    big = np.zeros((720, 1280, 3), np.uint8)
    for i in range(300):
        w.submit_frame(FramePacket.make(i, big.copy()))
    snap1 = tracemalloc.take_snapshot()
    for i in range(300, 1500):
        w.submit_frame(FramePacket.make(i, big.copy()))
    time.sleep(0.2)
    snap2 = tracemalloc.take_snapshot()
    w.stop()
    growth = sum(s.size_diff for s in snap2.compare_to(snap1, "filename"))
    tracemalloc.stop()
    assert growth < 30 * 1024 * 1024, growth
