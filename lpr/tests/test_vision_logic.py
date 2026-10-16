"""ตัวติดตามรถ, การโหวตหลายเฟรม, เส้นเสมือนและ ROI"""
from lpr.vision.geometry import crossing, net_side_motion, point_in_poly
from lpr.vision.tracker import ByteTracker
from lpr.vision.voting import Candidate, PlateVoter
from lpr.vision.yolo import Detection


def cand(norm, conf=0.9, sharp=100.0, prov="กรุงเทพมหานคร", valid=True):
    return Candidate(norm, norm, norm, prov, 100.0, conf, sharp, valid, "car", "white", "black", 2, 0.0)


def test_vote_majority():
    v = PlateVoter(15)
    for n in ["1กข4521"] * 6 + ["1กข4527"] * 2:
        v.add(cand(n))
    r = v.result()
    assert r.norm == "1กข4521" and r.province == "กรุงเทพมหานคร" and r.frames == 8
    assert r.alternatives[0]["plate_norm"] == "1กข4521" and len(r.alternatives) == 2


def test_vote_keeps_sharpest():
    v = PlateVoter(3)
    for s in [10, 50, 20, 80, 5]:
        v.add(cand("กข1", sharp=s))
    assert sorted(c.sharp for c in v.cands) == [20, 50, 80]


def test_vote_ambiguous_lowers_confidence():
    clear, amb = PlateVoter(), PlateVoter()
    for _ in range(8):
        clear.add(cand("จฬ1543", 0.92))
    for n in ["จฬ1543", "จพ1543"] * 4:
        amb.add(cand(n, 0.92))
    assert clear.result().confidence > 0.85
    assert amb.result().confidence < 0.8  # -> รอตรวจสอบ


def test_vote_unread():
    v = PlateVoter()
    v.add(cand(""))
    r = v.result()
    assert r.norm == "" and r.confidence == 0


def test_tracker_follows_moving_box():
    tr = ByteTracker(timeout_s=1.0)
    ids = set()
    for i in range(20):
        x = 100 + i * 8
        tracks, _ = tr.update([Detection(x, 100, x + 120, 180, 0.8, 2)], float(i) * 0.1)
        ids |= {t.id for t in tracks}
    assert ids == {1}
    _, ended = tr.update([], 5.0)
    assert [t.id for t in ended] == [1] and ended[0].hits == 20


def test_tracker_low_score_continues_track():
    tr = ByteTracker(high=0.5, low=0.1, timeout_s=1.0)
    tr.update([Detection(0, 0, 100, 100, 0.9, 2)], 0.0)
    tracks, _ = tr.update([Detection(5, 0, 105, 100, 0.2, 2)], 0.1)  # ความมั่นใจต่ำแต่ต่อ track เดิมได้
    assert len(tracks) == 1 and tracks[0].hits == 2
    tracks, _ = tr.update([Detection(500, 500, 600, 600, 0.2, 2)], 0.2)  # กล่องต่ำที่ไม่ตรงกับใคร ไม่สร้าง track ใหม่
    assert len(tracks) == 1


def test_two_cars_two_tracks():
    tr = ByteTracker()
    tracks, _ = tr.update([Detection(0, 0, 100, 100, 0.9, 2), Detection(300, 0, 400, 100, 0.9, 3)], 0.0)
    assert len(tracks) == 2


def test_line_crossing_direction():
    line = [(0.0, 0.5), (1.0, 0.5)]
    assert crossing(line, (0.5, 0.4), (0.5, 0.6)) == 1   # ลง
    assert crossing(line, (0.5, 0.6), (0.5, 0.4)) == -1  # ขึ้น
    assert crossing(line, (0.5, 0.1), (0.5, 0.3)) == 0
    short = [(0.0, 0.5), (0.3, 0.5)]
    assert crossing(short, (0.9, 0.4), (0.9, 0.6)) == 0  # ข้ามนอกช่วงของเส้น


def test_net_motion_without_line():
    assert net_side_motion([], (0.5, 0.2), (0.5, 0.8)) == 1
    assert net_side_motion([], (0.5, 0.8), (0.5, 0.2)) == -1


def test_point_in_poly():
    sq = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    assert point_in_poly(sq, 0.5, 0.5)
    assert not point_in_poly(sq, 0.95, 0.5)
    assert point_in_poly([], 0.99, 0.99)  # ไม่มี ROI = ทั้งภาพ


def test_pick_providers_gpu_order(monkeypatch):
    from lpr.vision import runtime

    monkeypatch.setattr(runtime, "available_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setattr(runtime, "best_adapter", lambda: None)
    assert runtime.pick_providers("auto") == ["CPUExecutionProvider"]  # ไม่มีการ์ดจอจริง ไม่ใช้ DirectML
    assert runtime.pick_providers("dml")[0] == "DmlExecutionProvider"
    monkeypatch.setattr(runtime, "best_adapter", lambda: {"index": 1, "name": "GPU", "vendor": "10de", "vram_mb": 8192})
    assert runtime.pick_providers("auto") == [("DmlExecutionProvider", {"device_id": 1}), "CPUExecutionProvider"]
    assert runtime.pick_providers("cpu") == ["CPUExecutionProvider"]
    monkeypatch.setattr(runtime, "available_providers", lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    assert runtime.pick_providers("auto") == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_gpu_fallback_to_cpu(monkeypatch, tmp_path):
    """ถ้า GPU ใช้ไม่ได้ ต้องกลับไปใช้ CPU และยังรันโมเดลได้"""
    from pathlib import Path

    from lpr.vision import runtime

    model = Path(__file__).resolve().parents[1] / "models" / "PP-OCRv5_mobile_det.onnx"
    if not model.exists():
        import pytest

        pytest.skip("ไม่มีไฟล์โมเดล")
    # ไม่มี build ไหนใน CI ที่มี CUDA จึงต้องตกไปใช้ CPU
    monkeypatch.setattr(runtime, "pick_providers", lambda d: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setattr(runtime, "_preload_cuda", lambda: None)
    sess = runtime.make_session(model, "auto")
    assert sess.get_providers()[0] == "CPUExecutionProvider"
    sess.run(None, runtime._dummy_feed(sess))
