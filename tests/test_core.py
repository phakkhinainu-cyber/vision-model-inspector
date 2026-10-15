"""Pure logic tests (numpy/OpenCV only)."""
import json
import os
import time

import numpy as np
import pytest

from vmi.core.classes import (ClassMappingError, ClassRegistry, ClassView, DisplayNameStore,
                              compare_mapping, load_mapping_file, normalize_names,
                              parse_literal_names)
from vmi.core.export import ExportOptions, export_snapshot, unique_path
from vmi.core.imageops import (box_iou, imread_unicode, imwrite_unicode, letterbox,
                               letterbox_boxes, nms, unletterbox_boxes, unletterbox_map,
                               yolo_raw_postprocess)
from vmi.core.snapshots import GradCamRecord, Snapshot, SnapshotStore
from vmi.core.types import (Detection, DetectionResult, InferenceSettings, ModelIdentity,
                            format_confidence)
from vmi.config import redact


# ---------------------------------------------------------------- letterbox
@pytest.mark.parametrize("shape,target,auto", [((480, 640), 640, False), ((720, 1280), 640, True),
                                               ((1000, 300), 320, False), ((333, 777), 416, True),
                                               ((640, 640), 640, False)])
def test_letterbox_roundtrip(shape, target, auto):
    img = np.zeros((*shape, 3), np.uint8)
    lb, info = letterbox(img, target, auto=auto)
    assert lb.shape[0] <= target and lb.shape[1] <= target
    if not auto:
        assert lb.shape[:2] == (target, target)
    else:
        assert lb.shape[0] % 32 == 0 and lb.shape[1] % 32 == 0
    boxes = np.array([[10, 20, 100, 200], [0, 0, shape[1], shape[0]]], float)
    back = unletterbox_boxes(letterbox_boxes(boxes, info), info)
    assert np.allclose(back, boxes, atol=1e-6)


def test_letterbox_maps_pixels_correctly():
    # a white square at a known place must land where letterbox_boxes says
    img = np.zeros((300, 900, 3), np.uint8)
    img[100:200, 400:500] = 255
    lb, info = letterbox(img, 640)
    b = letterbox_boxes([[400, 100, 500, 200]], info)[0]
    ys, xs = np.nonzero(lb[:, :, 0] > 128)
    assert abs(xs.min() - b[0]) <= 1.5 and abs(xs.max() + 1 - b[2]) <= 1.5
    assert abs(ys.min() - b[1]) <= 1.5 and abs(ys.max() + 1 - b[3]) <= 1.5


def test_unletterbox_map_shape():
    img = np.zeros((480, 640, 3), np.uint8)
    _, info = letterbox(img, 320)
    heat = np.random.rand(info.out_h // 8, info.out_w // 8).astype(np.float32)
    m = unletterbox_map(heat, info)
    assert m.shape == (480, 640)


def test_nms_and_postprocess():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], float)
    scores = np.array([0.9, 0.8, 0.7])
    assert list(nms(boxes, scores, 0.5)) == [0, 2]
    # raw head: 2 classes, 4 anchors (cx, cy, w, h)
    pred = np.zeros((6, 4), np.float32)
    pred[:4, 0] = [5, 5, 10, 10]; pred[4, 0] = 0.9
    pred[:4, 1] = [6, 6, 10, 10]; pred[4, 1] = 0.8           # overlaps anchor 0, same class
    pred[:4, 2] = [6, 6, 10, 10]; pred[5, 2] = 0.85          # overlaps but other class
    pred[:4, 3] = [100, 100, 10, 10]; pred[4, 3] = 0.1        # below threshold
    b, s, c, a = yolo_raw_postprocess(pred, 0.25, 0.45)
    assert list(a) == [0, 2] and list(c) == [0, 1]
    assert np.allclose(b[0], [0, 0, 10, 10])


def test_box_iou():
    assert box_iou([[0, 0, 10, 10]], [[0, 0, 10, 10]])[0, 0] == pytest.approx(1.0)
    assert box_iou([[0, 0, 10, 10]], [[20, 20, 30, 30]])[0, 0] == 0


# ---------------------------------------------------------------- classes
def test_mapping_files(tmp_path):
    y = tmp_path / "data.yaml"
    y.write_text("nc: 3\nnames: ['ok', 'รอยร้าว', 'สนิม']\n", encoding="utf-8")
    assert load_mapping_file(str(y)) == {0: "ok", 1: "รอยร้าว", 2: "สนิม"}
    y2 = tmp_path / "d2.yaml"
    y2.write_text("names:\n  0: a\n  1: b\n", encoding="utf-8")
    assert load_mapping_file(str(y2)) == {0: "a", 1: "b"}
    t = tmp_path / "classes.txt"
    t.write_text("พริกดี\nพริกเสีย\n\n", encoding="utf-8")
    assert load_mapping_file(str(t)) == {0: "พริกดี", 1: "พริกเสีย"}
    j = tmp_path / "m.json"
    j.write_text(json.dumps({"0": "x", "1": "y"}), encoding="utf-8")
    assert load_mapping_file(str(j)) == {0: "x", 1: "y"}


@pytest.mark.parametrize("content,ext", [
    ("nc: 2\nnames: [a, b, c]\n", ".yaml"),            # nc contradicts names
    ("names: {0: a, 2: b}\n", ".yaml"),                 # non contiguous
    ("names: [a, b\n", ".yaml"),                        # broken yaml
    ("foo: 1\n", ".yaml"),                              # no names
    ("a\n\nb\n", ".txt"),                               # blank line in the middle
    ("{bad json", ".json"),
    ("!!python/object/apply:os.system ['echo hi']", ".yaml"),   # unsafe yaml must not run
])
def test_mapping_errors(tmp_path, content, ext):
    p = tmp_path / f"bad{ext}"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(ClassMappingError):
        load_mapping_file(str(p))


def test_compare_mapping_and_literal():
    cur = {0: "person", 1: "car"}
    with pytest.raises(ClassMappingError):
        compare_mapping(cur, {0: "a"}, expected_count=2)
    diffs = compare_mapping(cur, {0: "คน", 1: "car"}, expected_count=2)
    assert diffs == [(0, "person", "คน")]
    assert parse_literal_names("{0: 'person', 1: 'car'}") == cur
    with pytest.raises(ClassMappingError):
        parse_literal_names("__import__('os').system('x')")


def test_registry_generated_and_generic():
    r = ClassRegistry.generated(3, verified=True)
    assert r.name(2) == "class_2" and not r.names_available
    g = ClassRegistry(normalize_names(["0", "1"]), "model")
    assert g.looks_generic()
    assert not ClassRegistry({0: "person"}, "model").looks_generic()


def test_display_store(tmp_path):
    st = DisplayNameStore(str(tmp_path / "dn.json"))
    st.set_display_names("abc", {0: "คน", 1: ""})
    st.set_hidden("abc", {1})
    st2 = DisplayNameStore(str(tmp_path / "dn.json"))
    assert st2.display_names("abc") == {0: "คน"}
    assert st2.hidden("abc") == {1}
    assert st2.display_names("other") == {}          # other model unaffected
    v = ClassView(ClassRegistry({0: "person", 1: "car"}, "model"), st2.display_names("abc"),
                  st2.hidden("abc"))
    assert v.label(0) == "คน" and v.label(1) == "car" and not v.visible(1)


# ---------------------------------------------------------------- snapshots / export
def _snap(idx=1, w=320, h=240, n=2, with_cam=False):
    ident = ModelIdentity("m.pt", "/x/m.pt", "f" * 64, "ultralytics-pt", ".pt")
    dets = [Detection(i, i % 2, 0.5 + i * 0.1, (10 + i * 30, 10, 40 + i * 30, 60)) for i in range(n)]
    res = DetectionResult(idx, time.time(), (w, h), dets, 12.3, ident, InferenceSettings(), "cpu")
    s = Snapshot(idx, np.full((h, w, 3), 80, np.uint8), res, {0: "person", 1: "แก้ว"}, "model",
                 {0: "คน"}, {1}, "test")
    if with_cam:
        s.gradcam = GradCamRecord(0, 0, 0.5, dets[0].box, "auto", "layer 15",
                                  np.random.rand(h, w).astype(np.float32), {"match_iou": 0.99})
    return s


def test_snapshot_store_bounds():
    st = SnapshotStore(max_items=5, max_mb=512)
    ev = []
    for i in range(12):
        ev += st.add(_snap(st.next_index()))
    assert len(st) == 5 and len(ev) == 7
    assert [s.index for s in st.all()] == [8, 9, 10, 11, 12]
    st.set_limits(5, 16)  # 16 MB; each is 230 KB -> still 5
    big = SnapshotStore(max_items=100, max_mb=16)
    for i in range(40):
        big.add(_snap(big.next_index(), 1280, 720))   # 2.7 MB each
    assert big.total_bytes <= 16 * 1024 * 1024 and len(big) <= 6
    assert st.remove(10) and st.get(10) is None


def test_snapshot_labels_survive_model_change():
    s = _snap()
    assert s.label(0) == "คน" and s.label(1) == "แก้ว"
    assert [d.det_id for d in s.visible_detections()] == [0]


def test_export_thai_paths_no_overwrite(tmp_path):
    out = tmp_path / "ผลการ ส่งออก"
    out.mkdir()
    s = _snap(3, with_cam=True)
    f1 = export_snapshot(s, str(out), ExportOptions())
    f2 = export_snapshot(s, str(out), ExportOptions())
    assert len(f1) == 7 and len(f2) == 7
    assert os.path.dirname(f1[0]) != os.path.dirname(f2[0])       # second export = new folder
    for p in f1:
        assert os.path.getsize(p) > 0
    img = imread_unicode(f1[0])
    assert img.shape == (240, 320, 3)
    meta = json.load(open([p for p in f1 if p.endswith(".json")][0], encoding="utf-8"))
    assert meta["model"]["sha256"] == "f" * 64
    assert meta["gradcam"]["layer"] == "layer 15"
    assert meta["class_mapping"]["classes"][1]["original_name"] == "แก้ว"
    assert "dependencies" in meta and "python" in meta["dependencies"]
    csv_text = open([p for p in f1 if p.endswith(".csv")][0], encoding="utf-8-sig").read()
    assert "แก้ว" in csv_text and "0.60" in csv_text


def test_unique_path(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"x")
    assert unique_path(str(p)).endswith("a (2).png")


def test_imwrite_unicode(tmp_path):
    p = str(tmp_path / "ภาพ ทดสอบ.png")
    imwrite_unicode(p, np.zeros((5, 5, 3), np.uint8))
    assert imread_unicode(p).shape == (5, 5, 3)


def test_format_confidence_and_redact():
    assert format_confidence(0.876) == "0.88"
    r = redact("open rtsp://admin:secret@10.0.0.2:554/stream password=abc")
    assert "secret" not in r and "abc" not in r and "10.0.0.2" in r
