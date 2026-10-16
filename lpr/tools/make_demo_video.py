"""สร้างวิดีโอตัวอย่างสำหรับโหมดจำลอง: รถวิ่งเข้าหากล้องทีละคัน พร้อมป้ายทะเบียนไทยจำลอง

python tools/make_demo_video.py --images work/testdata --out work/demo/demo.mp4 --cars 6
ผลลัพธ์: วิดีโอ + ไฟล์ .json เฉลยป้ายทะเบียนของรถแต่ละคัน (ใช้ทดสอบอัตโนมัติ)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from synth_plates import degrade, random_plate, render_plate  # noqa: E402

from lpr.vision.yolo import COCO_VEHICLES, YoloDetector  # noqa: E402


def road(w: int, h: int) -> np.ndarray:
    img = np.full((h, w, 3), (92, 96, 98), np.uint8)
    rng = np.random.default_rng(0)
    img = np.clip(img.astype(np.int16) + rng.normal(0, 7, img.shape), 0, 255).astype(np.uint8)
    cv2.rectangle(img, (0, 0), (w, int(h * 0.18)), (180, 170, 150), -1)  # กำแพง/รั้ว
    for x in range(0, w, 90):
        cv2.rectangle(img, (x, int(h * 0.04)), (x + 12, int(h * 0.18)), (70, 70, 70), -1)
    cv2.line(img, (int(w * 0.08), h), (int(w * 0.3), int(h * 0.18)), (230, 230, 230), 4)
    cv2.line(img, (int(w * 0.92), h), (int(w * 0.7), int(h * 0.18)), (230, 230, 230), 4)
    return cv2.GaussianBlur(img, (3, 3), 0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default="work/testdata")
    ap.add_argument("--out", default="work/demo/demo.mp4")
    ap.add_argument("--cars", type=int, default=6)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--size", default="960x540")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--model", default=str(ROOT / "models" / "vehicle_yolo11n.onnx"))
    a = ap.parse_args()
    W, H = map(int, a.size.split("x"))
    rng = random.Random(a.seed)
    src = Path(a.images)
    plates = json.loads((src / "plates.json").read_text("utf-8"))
    det = YoloDetector(Path(a.model))
    cars = []
    for name, info in plates.items():
        img = cv2.imread(str(src / "images" / name))
        if img is None:
            continue
        x, y, w, h = info["bbox_xywh"]
        pcx, pcy = x + w / 2, y + h / 2
        best = None
        for d in det.detect(img, conf=0.4, classes=set(COCO_VEHICLES)):
            if d.x1 <= pcx <= d.x2 and d.y1 <= pcy <= d.y2 and d.w > 2.2 * w:
                if best is None or d.w * d.h > best.w * best.h:
                    best = d
        if best is None or best.w < 0.45 * img.shape[1]:
            continue
        kind = "public" if rng.random() < 0.15 else "car"
        style = rng.choice(["white_black", "white_black", "white_green", "white_blue"]) if kind == "car" else "yellow_black"
        top, norm, prov = random_plate(rng, kind)
        plate = render_plate(top, prov, style, width=300)
        pw = int(w * 1.05)
        ph = int(pw * plate.shape[0] / plate.shape[1])
        px0, py0 = int(pcx - pw / 2), int(pcy - ph / 2)
        if px0 < 0 or py0 < 0 or px0 + pw > img.shape[1] or py0 + ph > img.shape[0]:
            continue
        img[py0:py0 + ph, px0:px0 + pw] = degrade(cv2.resize(plate, (pw, ph), interpolation=cv2.INTER_AREA),
                                                   rng, 0.4)
        x1, y1, x2, y2 = int(best.x1), int(best.y1), int(best.x2), int(best.y2)
        cars.append({"img": img[y1:y2, x1:x2].copy(), "plate_norm": norm, "province": prov, "style": style,
                     "source": name})
        if len(cars) >= a.cars:
            break
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (W, H))
    bg = road(W, H)
    truth = []
    t = 0.0
    for _ in range(int(a.fps * 1.5)):
        vw.write(bg)
        t += 1 / a.fps
    for c in cars:
        n = int(a.fps * 3.2)
        t_start = t
        for i in range(n):
            k = i / (n - 1)
            scale = 0.45 + 0.55 * k  # รถวิ่งเข้าหากล้อง: เล็ก -> ใหญ่ และเลื่อนลง
            cw = int(W * 0.62 * scale)
            ch = int(cw * c["img"].shape[0] / c["img"].shape[1])
            car = cv2.resize(c["img"], (cw, ch), interpolation=cv2.INTER_AREA)
            cx = int(W / 2 - cw / 2 + (k - 0.5) * W * 0.06)
            cy = int(H * 0.22 + k * (H * 0.95 - ch) - H * 0.05)
            f = bg.copy()
            y0, x0 = max(0, cy), max(0, cx)
            y1, x1 = min(H, cy + ch), min(W, cx + cw)
            f[y0:y1, x0:x1] = car[y0 - cy:y1 - cy, x0 - cx:x1 - cx]
            vw.write(f)
            t += 1 / a.fps
        truth.append({"plate_norm": c["plate_norm"], "province": c["province"], "style": c["style"],
                      "t_start": round(t_start, 2), "t_end": round(t, 2), "source": c["source"]})
        for _ in range(int(a.fps * 1.8)):
            vw.write(bg)
            t += 1 / a.fps
    vw.release()
    out.with_suffix(".json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), "utf-8")
    print(f"wrote {out} ({len(cars)} cars, {t:.1f} s)")
    for x in truth:
        print("  ", x["plate_norm"], x["province"], x["style"], x["source"])


if __name__ == "__main__":
    main()
