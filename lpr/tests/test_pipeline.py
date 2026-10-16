"""ทดสอบขั้นตอนประมวลผลทั้งหมดกับวิดีโอตัวอย่าง (ข้ามถ้าไม่มีไฟล์โมเดล)"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
DEMO = ROOT / "work" / "demo" / "demo.mp4"
sys.path.insert(0, str(ROOT / "tools"))

need_models = pytest.mark.skipif(not (MODELS / "vehicle_yolo11n.onnx").exists(), reason="ไม่มีไฟล์โมเดล")


@need_models
def test_reader_on_synthetic_plates(tmp_path):
    import random

    from synth_plates import degrade, random_plate, render_plate

    from lpr.vision.ocr import create_engine
    from lpr.vision.reader import PlateReader

    eng = create_engine("auto", MODELS / "th_PP-OCRv5_mobile_rec.onnx", MODELS / "th_PP-OCRv5_mobile_rec.dict.txt")
    reader = PlateReader(eng)
    rng = random.Random(3)
    ok = 0
    for _ in range(20):
        top, norm, prov = random_plate(rng)
        r = reader.read(degrade(render_plate(top, prov, width=rng.randint(160, 320)), rng))
        ok += r.parsed.norm == norm and r.parsed.province == prov
    assert ok >= 17, ok


@need_models
@pytest.mark.skipif(not DEMO.exists(), reason="ยังไม่ได้สร้างวิดีโอตัวอย่าง (tools/make_demo_video.py)")
def test_pipeline_on_demo_video():
    from eval_video import run

    events, stats = run(DEMO, MODELS, [[0.05, 0.6], [0.95, 0.6]])
    truth = json.loads(DEMO.with_suffix(".json").read_text("utf-8"))
    found = sum(1 for t in truth if any(e["plate_norm"] == t["plate_norm"] for e in events))
    assert found >= len(truth) - 1
    assert len(events) <= len(truth) + 1
    assert all(e["direction"] == "เข้า" for e in events)
    assert all(e["full_jpg"] for e in events)
