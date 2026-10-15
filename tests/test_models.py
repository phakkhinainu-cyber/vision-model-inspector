"""Tests with real models (need torch + ultralytics + onnxruntime and test_assets).

Run ``python tools/make_test_assets.py`` first. All tests run on CPU.
"""
import os

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("ultralytics")

from conftest import ASSETS_DIR, model_path  # noqa: E402
from vmi.adapters.base import DeviceUnavailableError, UnsupportedModelError  # noqa: E402
from vmi.adapters.onnx_adapter import OnnxYoloAdapter  # noqa: E402
from vmi.adapters.registry import create_adapter  # noqa: E402
from vmi.adapters.ultralytics_adapter import UltralyticsAdapter  # noqa: E402
from vmi.core.classes import (ClassMappingError, SOURCE_GENERATED, SOURCE_MODEL, SOURCE_ONNX,  # noqa: E402
                              compare_mapping, load_mapping_file)
from vmi.core.imageops import box_iou, imread_unicode  # noqa: E402
from vmi.core.snapshots import Snapshot  # noqa: E402
from vmi.core.types import FramePacket, InferenceSettings  # noqa: E402
from vmi.gradcam.ultralytics_gradcam import GradCamError  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(model_path("yolov8n.pt")),
                                reason="test assets missing (run tools/make_test_assets.py)")

S = InferenceSettings(conf=0.25, iou=0.45, imgsz=640, device="cpu")


def bus():
    return imread_unicode(os.path.join(ASSETS_DIR, "images", "bus.jpg"))


@pytest.fixture(scope="module")
def v8():
    a = UltralyticsAdapter()
    a.load(model_path("yolov8n.pt"), "cpu")
    yield a
    a.close()


@pytest.fixture(scope="module")
def v11():
    a = UltralyticsAdapter()
    a.load(model_path("yolo11n.pt"), "cpu")
    yield a
    a.close()


@pytest.fixture(scope="module")
def onnx_v8():
    a = OnnxYoloAdapter()
    a.load(model_path("yolov8n.onnx"), "cpu")
    yield a
    a.close()


# ---------------------------------------------------------------- loading / classes
def test_two_models_with_different_classes(v8):
    custom = UltralyticsAdapter()
    info = custom.load(model_path("custom3_untrained.pt"), "cpu")
    assert info.classes.count == 3 and info.classes.source == SOURCE_MODEL
    assert info.classes.names == {0: "ชิ้นงานดี", 1: "รอยร้าว", 2: "สนิม"}
    assert v8.info.classes.count == 80 and v8.info.classes.count_verified
    assert v8.info.identity.sha256 != info.identity.sha256
    custom.close()


def test_yolo11_supported(v11):
    assert v11.info.caps.grad_cam and v11.info.details["ตระกูลโมเดล"] == "yolo11"
    dets = v11.predict(bus(), S)
    assert len(dets) >= 3


def test_registry_dispatch_and_unsupported(tmp_path):
    assert isinstance(create_adapter("a.pt"), UltralyticsAdapter)
    assert isinstance(create_adapter("a.onnx"), OnnxYoloAdapter)
    with pytest.raises(UnsupportedModelError):
        create_adapter("model.h5")
    bad = tmp_path / "broken.pt"
    bad.write_bytes(os.urandom(2048))
    with pytest.raises(UnsupportedModelError):
        UltralyticsAdapter().load(str(bad), "cpu")
    bad2 = tmp_path / "broken.onnx"
    bad2.write_bytes(b"not an onnx file")
    with pytest.raises(UnsupportedModelError):
        OnnxYoloAdapter().load(str(bad2), "cpu")


def test_classification_model_rejected():
    p = model_path("yolov8n-cls.pt")
    if not os.path.exists(p):
        pytest.skip("yolov8n-cls.pt not downloaded")
    with pytest.raises(UnsupportedModelError, match="Object Detection"):
        UltralyticsAdapter().load(p, "cpu")


def test_cuda_request_without_gpu():
    if torch.cuda.is_available():
        pytest.skip("machine has CUDA")
    with pytest.raises(DeviceUnavailableError):
        UltralyticsAdapter().load(model_path("yolov8n.pt"), "cuda")


def test_onnx_metadata_and_no_names(onnx_v8, v8, tmp_path):
    assert onnx_v8.info.classes.source == SOURCE_ONNX
    assert onnx_v8.info.classes.names == v8.info.classes.names
    bare = OnnxYoloAdapter()
    info = bare.load(model_path("yolov8n_nonames.onnx"), "cpu")
    assert info.classes.source == SOURCE_GENERATED and info.classes.count == 80
    assert info.classes.name(5) == "class_5" and info.classes.count_verified
    # import a correct mapping
    txt = tmp_path / "classes.txt"
    txt.write_text("\n".join(v8.info.classes.names[i] for i in range(80)), encoding="utf-8")
    names = load_mapping_file(str(txt))
    diffs = compare_mapping(info.classes.names, names, bare.output_class_count())
    assert len(diffs) == 80
    # wrong count must be rejected
    bad = tmp_path / "data.yaml"
    bad.write_text("names: [a, b, c]\n", encoding="utf-8")
    with pytest.raises(ClassMappingError):
        compare_mapping(info.classes.names, load_mapping_file(str(bad)), bare.output_class_count())
    assert bare.gradcam_engine() is None and "ONNX" in info.gradcam_status
    bare.close()


# ---------------------------------------------------------------- coordinates
def _match(a, b):
    """For each detection in a, IoU with best same-class detection in b."""
    out = []
    for d in a:
        same = [e for e in b if e.class_id == d.class_id]
        out.append(max([box_iou([d.box], [e.box])[0, 0] for e in same], default=0))
    return np.array(out)


def test_boxes_in_original_coordinates_after_letterbox(v8):
    img = bus()
    base = [d for d in v8.predict(img, S) if d.confidence > 0.5]
    assert base
    # 1) pad 120 px left and 60 px top -> boxes shift exactly
    padded = np.pad(img, ((60, 0), (120, 0), (0, 0)), constant_values=114)
    moved = v8.predict(padded, S)
    for d in base:
        x1, y1, x2, y2 = d.box
        shifted = (x1 + 120, y1 + 60, x2 + 120, y2 + 60)
        best = max(box_iou([shifted], [e.box])[0, 0] for e in moved if e.class_id == d.class_id)
        assert best > 0.85
    # 2) half-size image -> boxes scale by 0.5
    import cv2
    small = cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2))
    sd = v8.predict(small, S)
    for d in base:
        half = tuple(v / 2 for v in d.box)
        best = max(box_iou([half], [e.box])[0, 0] for e in sd if e.class_id == d.class_id)
        assert best > 0.8
    for d in v8.predict(img, S):
        x1, y1, x2, y2 = d.box
        assert 0 <= x1 < x2 <= img.shape[1] and 0 <= y1 < y2 <= img.shape[0]


def test_onnx_matches_pytorch(v8, onnx_v8):
    img = bus()
    a = [d for d in v8.predict(img, S) if d.confidence > 0.4]
    b = onnx_v8.predict(img, S)
    ious = _match(a, b)
    assert (ious > 0.9).mean() >= 0.8, ious


# ---------------------------------------------------------------- Grad-CAM
def test_gradcam_enabled_for_v8_and_v11(v8, v11):
    assert v8.info.caps.grad_cam, v8.info.caps.grad_cam_reason
    assert v11.info.caps.grad_cam, v11.info.caps.grad_cam_reason
    assert v8.info.details["ตระกูลโมเดล"] == "yolov8"


def test_gradcam_target_matching_every_detection(v8):
    img = bus()
    eng = v8.gradcam_engine()
    dets = v8.predict(img, S)
    for d in dets:
        out = eng.compute(img, d, S.imgsz, "auto")
        assert out.heatmap.shape == img.shape[:2]
        assert out.details["match_iou"] > 0.95, out.details
        assert out.details["score_difference"] < 0.02, out.details
        assert 0 < out.heatmap.max() <= 1


def test_gradcam_same_class_different_instances(v8):
    """Two people (same class) -> different target scalars -> different maps.

    Standard Grad-CAM averages gradients spatially, so it may highlight every
    person; we only require the maps to differ. HiResCAM keeps the spatial
    gradient and must be strongest inside the selected person's own box.
    """
    img = bus()
    people = sorted([d for d in v8.predict(img, S) if v8.info.classes.name(d.class_id) == "person"
                     and d.confidence > 0.5], key=lambda d: d.box[0])
    assert len(people) >= 2, "bus.jpg should contain several people"
    eng = v8.gradcam_engine()
    a, b = people[0], people[-1]

    def mean_in(h, box):
        x1, y1, x2, y2 = (int(v) for v in box)
        return float(h[y1:y2, x1:x2].mean())

    ga = eng.compute(img, a, 640, "auto", "gradcam").heatmap
    gb = eng.compute(img, b, 640, "auto", "gradcam").heatmap
    assert not np.allclose(ga, gb, atol=1e-3)
    ha = eng.compute(img, a, 640, "auto", "hirescam").heatmap
    hb = eng.compute(img, b, 640, "auto", "hirescam").heatmap
    assert np.corrcoef(ha.ravel(), hb.ravel())[0, 1] < 0.9
    assert mean_in(ha, a.box) > mean_in(ha, b.box)
    assert mean_in(hb, b.box) > mean_in(hb, a.box)


def test_gradcam_layers_never_fake(v8):
    img = bus()
    d = max(v8.predict(img, S), key=lambda x: x.confidence)
    eng = v8.gradcam_engine()
    opts = eng.layer_options()
    assert opts[0][0] == "auto" and len(opts) >= 4
    for key, _label in opts:
        try:
            out = eng.compute(img, d, 640, key)
            assert out.heatmap.max() > 0
        except GradCamError as e:          # allowed: honest refusal, never a fake map
            assert str(e)


def test_gradcam_unmatched_target_is_refused(v8):
    from vmi.core.types import Detection
    img = bus()
    fake = Detection(0, 0, 0.9, (1.0, 1.0, 6.0, 6.0))       # nothing there
    with pytest.raises(GradCamError):
        v8.gradcam_engine().compute(img, fake, 640)


def test_snapshot_keeps_model_identity(v8):
    from vmi.pipeline.inference_worker import InferenceWorker
    import threading
    custom = UltralyticsAdapter()
    custom.load(model_path("custom3_untrained.pt"), "cpu")
    got, ev = [], threading.Event()
    w = InferenceWorker(on_result=lambda p, r, k, t: (got.append((p, r)), ev.set()))
    w.set_settings(S)
    w.set_adapter(v8)
    w.start()
    w.submit_job(FramePacket.make(1, bus()))
    assert ev.wait(60)
    pkt, res = got[0]
    snap = Snapshot(1, pkt.image.copy(), res, dict(v8.info.classes.names), v8.info.classes.source,
                    {}, set(), "bus.jpg")
    ev.clear()
    w.set_adapter(custom)                     # change model
    w.submit_job(FramePacket.make(2, bus()))
    assert ev.wait(60)
    w.stop()
    assert snap.result.model.sha256 == v8.info.identity.sha256
    assert got[1][1].model.sha256 == custom.info.identity.sha256
    assert snap.label(0) == "person"           # old snapshot not relabelled
    custom.close()
