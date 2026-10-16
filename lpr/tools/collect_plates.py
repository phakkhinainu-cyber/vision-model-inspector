"""เก็บภาพป้ายทะเบียนจากกล้องจริง (หรือไฟล์วิดีโอ) ไว้ใช้ fine-tune โมเดล

ผลลัพธ์ในโฟลเดอร์ --out:
  frames/xxx.jpg + frames/xxx.txt   ภาพเต็มเฟรม + กรอบป้ายแบบ YOLO (class 0 = license_plate) สำหรับฝึกตัวตรวจจับป้าย
  plates/xxx.jpg                     ภาพป้ายที่ครอปแล้ว
  labels.tsv                         ชื่อไฟล์ป้าย<TAB>ทะเบียนที่ระบบอ่านได้<TAB>จังหวัด  -> ให้คนตรวจแก้ แล้วใช้ฝึก OCR

python tools/collect_plates.py "rtsp://user:pass@192.168.1.20:554/stream1" --out D:\\LPR\\dataset --minutes 60
python tools/collect_plates.py gate.mp4 --out dataset --every 0.5

(ในโปรแกรมสามารถเปิด "เก็บภาพป้ายไว้ฝึกโมเดล" ในหน้าตั้งค่า ระบบจะเก็บภาพป้ายไว้ที่ <ที่เก็บข้อมูล>\\dataset อัตโนมัติ)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lpr.camera.stream import open_capture  # noqa: E402
from lpr.config import MODEL_FILES  # noqa: E402
from lpr.vision.ocr import create_engine  # noqa: E402
from lpr.vision.plate_detect import PlateDetector  # noqa: E402
from lpr.vision.preprocess import sharpness  # noqa: E402
from lpr.vision.reader import PlateReader  # noqa: E402
from lpr.vision.yolo import COCO_VEHICLES, YoloDetector  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--every", type=float, default=1.0, help="ตรวจทุกกี่วินาที")
    ap.add_argument("--minutes", type=float, default=0, help="หยุดหลังกี่นาที (0 = จนจบไฟล์/กด Ctrl+C)")
    ap.add_argument("--min-sharpness", type=float, default=60)
    ap.add_argument("--models", default=str(ROOT / "models"))
    a = ap.parse_args()
    m = Path(a.models)
    out = Path(a.out)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    (out / "plates").mkdir(parents=True, exist_ok=True)
    vehicle = YoloDetector(m / MODEL_FILES["vehicle"])
    plate = PlateDetector(m / MODEL_FILES["plate"] if (m / MODEL_FILES["plate"]).exists() else None)
    reader = PlateReader(create_engine("auto", m / MODEL_FILES["ocr_rec"], m / MODEL_FILES["ocr_dict"]))
    cap = open_capture(a.source)
    if not cap.isOpened():
        print("เปิดแหล่งภาพไม่ได้")
        return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    is_file = "://" not in a.source
    step = max(1, int(round(fps * a.every))) if is_file else 1
    t_end = time.time() + a.minutes * 60 if a.minutes else None
    last = 0.0
    saved = 0
    i = 0
    with open(out / "labels.tsv", "a", encoding="utf-8") as lab:
        while True:
            ok, frame = cap.read()
            if not ok:
                if is_file:
                    break
                time.sleep(0.5)
                continue
            i += 1
            if is_file and i % step:
                continue
            if not is_file and time.time() - last < a.every:
                continue
            last = time.time()
            h, w = frame.shape[:2]
            yolo_lines = []
            crops = []
            for d in vehicle.detect(frame, conf=0.35, classes=set(COCO_VEHICLES), agnostic=True):
                x1, y1, x2, y2 = int(d.x1), int(d.y1), int(d.x2), int(d.y2)
                pb = plate.detect(frame[y1:y2, x1:x2])
                if pb is None:
                    continue
                px1, py1, px2, py2 = x1 + pb.x1, y1 + pb.y1, x1 + pb.x2, y1 + pb.y2
                yolo_lines.append(f"0 {(px1 + px2) / 2 / w:.6f} {(py1 + py2) / 2 / h:.6f} {(px2 - px1) / w:.6f} {(py2 - py1) / h:.6f}")
                crop = frame[max(0, py1 - 3):py2 + 3, max(0, px1 - 3):px2 + 3]
                if sharpness(crop) >= a.min_sharpness:
                    crops.append(crop)
            if not yolo_lines:
                continue
            stamp = f"{int(time.time() * 1000)}_{i}"
            cv2.imwrite(str(out / "frames" / f"{stamp}.jpg"), frame)
            (out / "frames" / f"{stamp}.txt").write_text("\n".join(yolo_lines) + "\n")
            for k, crop in enumerate(crops):
                name = f"{stamp}_{k}.jpg"
                cv2.imwrite(str(out / "plates" / name), crop)
                r = reader.read(crop).parsed
                lab.write(f"plates/{name}\t{r.display}\t{r.province or ''}\n")
                saved += 1
            print(f"เก็บแล้ว {saved} ป้าย", end="\r")
            if t_end and time.time() > t_end:
                break
    print(f"\nเสร็จ: {saved} ป้าย ที่ {out} — ตรวจแก้ labels.tsv ให้ถูกต้องก่อนนำไปฝึก (ดู docs/fine-tune.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
