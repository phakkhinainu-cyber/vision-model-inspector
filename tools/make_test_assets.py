"""Create the test assets used by tests and screenshot scripts.

Expects test_assets/models/yolov8n.pt and yolo11n.pt (downloaded from the
official Ultralytics GitHub release by the CI workflow / build script).
Creates:
  * custom3_untrained.pt    — YOLOv8n structure, 3 Thai-named classes, untrained
                              (only for class-metadata tests; detections are meaningless)
  * yolov8n.onnx            — Ultralytics ONNX export (static 640, with metadata)
  * yolov8n_nonames.onnx    — same, with all metadata removed
  * images/bus.jpg, zidane.jpg (copied from the ultralytics package)
  * demo.avi                — short pan over bus.jpg for the live-preview demo
"""
from __future__ import annotations

import os
import shutil
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "test_assets")
MODELS = os.path.join(ASSETS, "models")
IMAGES = os.path.join(ASSETS, "images")

os.environ.setdefault("YOLO_OFFLINE", "True")
os.environ.setdefault("YOLO_AUTOINSTALL", "False")


def custom_model():
    out = os.path.join(MODELS, "custom3_untrained.pt")
    if os.path.exists(out):
        return out
    import torch
    import ultralytics
    from ultralytics.nn.tasks import DetectionModel
    torch.manual_seed(0)
    m = DetectionModel("yolov8n.yaml", nc=3, verbose=False)
    m.names = {0: "ชิ้นงานดี", 1: "รอยร้าว", 2: "สนิม"}
    m.eval()
    torch.save({"model": m.half(), "train_args": {}, "version": ultralytics.__version__,
                "date": "test"}, out)
    return out


def onnx_models():
    import onnx
    from ultralytics import YOLO
    src = os.path.join(MODELS, "yolov8n.pt")
    dst = os.path.join(MODELS, "yolov8n.onnx")
    if not os.path.exists(dst):
        p = YOLO(src).export(format="onnx", imgsz=640, dynamic=False, simplify=False, opset=17)
        if os.path.abspath(p) != os.path.abspath(dst):
            shutil.move(p, dst)
    bare = os.path.join(MODELS, "yolov8n_nonames.onnx")
    if not os.path.exists(bare):
        m = onnx.load(dst)
        del m.metadata_props[:]
        onnx.save(m, bare)
    return dst, bare


def images():
    import ultralytics
    os.makedirs(IMAGES, exist_ok=True)
    pkg = os.path.join(os.path.dirname(ultralytics.__file__), "assets")
    for n in ("bus.jpg", "zidane.jpg"):
        d = os.path.join(IMAGES, n)
        if not os.path.exists(d):
            shutil.copy(os.path.join(pkg, n), d)


def demo_video():
    out = os.path.join(ASSETS, "demo.avi")
    if os.path.exists(out):
        return out
    img = cv2.imread(os.path.join(IMAGES, "bus.jpg"))
    h, w = img.shape[:2]
    W, H = 960, 720
    canvas = cv2.resize(img, (int(w * H / h * 1.25), int(H * 1.25)))
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"MJPG"), 25, (W, H))
    if not vw.isOpened():
        raise RuntimeError("cannot create demo video")
    n = 150
    for i in range(n):
        t = 0.5 - 0.5 * np.cos(2 * np.pi * i / n)
        x = int(t * (canvas.shape[1] - W))
        y = int(t * (canvas.shape[0] - H) * 0.5)
        vw.write(canvas[y:y + H, x:x + W])
    vw.release()
    cap = cv2.VideoCapture(out)
    ok, _ = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("demo video is not readable")
    return out


def main():
    os.makedirs(MODELS, exist_ok=True)
    for n in ("yolov8n.pt", "yolo11n.pt"):
        if not os.path.exists(os.path.join(MODELS, n)):
            print(f"missing {n} in {MODELS}", file=sys.stderr)
            sys.exit(1)
    images()
    custom_model()
    onnx_models()
    demo_video()
    print("assets ready in", ASSETS)


if __name__ == "__main__":
    main()
