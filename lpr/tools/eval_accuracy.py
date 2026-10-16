"""วัดความแม่นยำการอ่านป้ายกับโฟลเดอร์ภาพตัวอย่าง

โฟลเดอร์ภาพ: ภาพรถ (.jpg/.png) + ไฟล์เฉลย labels.tsv (ชื่อไฟล์<TAB>ทะเบียน<TAB>จังหวัด)
ถ้าไม่มี labels.tsv จะใช้ชื่อไฟล์เป็นเฉลย เช่น "1กข4521_กรุงเทพมหานคร.jpg"
ภาพอาจเป็นภาพทั้งคัน (จะหาป้ายให้) หรือภาพป้ายที่ครอปแล้ว (--crops)

python tools/eval_accuracy.py โฟลเดอร์ภาพ [--crops] [--report report.csv]
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lpr.config import MODEL_FILES  # noqa: E402
from lpr.plates.parser import normalize_plate_text  # noqa: E402
from lpr.vision.ocr import create_engine  # noqa: E402
from lpr.vision.ocr.textdet import DbTextDetector  # noqa: E402
from lpr.vision.plate_detect import PlateDetector  # noqa: E402
from lpr.vision.reader import PlateReader  # noqa: E402
from lpr.vision.yolo import COCO_VEHICLES, YoloDetector  # noqa: E402


def load_labels(folder: Path) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    tsv = folder / "labels.tsv"
    if tsv.exists():
        for line in tsv.read_text("utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and not line.startswith("#"):
                out[parts[0]] = (normalize_plate_text(parts[1])[0], parts[2].strip() if len(parts) > 2 else "")
        return out
    for p in folder.iterdir():
        if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            stem = p.stem.split("_")
            out[p.name] = (normalize_plate_text(stem[0])[0], stem[1] if len(stem) > 1 else "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--crops", action="store_true", help="ภาพในโฟลเดอร์เป็นภาพป้ายที่ครอปแล้ว")
    ap.add_argument("--models", default=str(ROOT / "models"))
    ap.add_argument("--report", default="")
    a = ap.parse_args()
    folder, m = Path(a.folder), Path(a.models)
    labels = load_labels(folder)
    if not labels:
        print("ไม่พบภาพหรือเฉลย")
        return 1
    ocr = create_engine("auto", m / MODEL_FILES["ocr_rec"], m / MODEL_FILES["ocr_dict"])
    det = DbTextDetector(m / MODEL_FILES["ocr_det"]) if (m / MODEL_FILES["ocr_det"]).exists() else None
    reader = PlateReader(ocr, det)
    vehicle = None if a.crops else YoloDetector(m / MODEL_FILES["vehicle"])
    plate = None if a.crops else PlateDetector(m / MODEL_FILES["plate"] if (m / MODEL_FILES["plate"]).exists() else None)
    rows = []
    t0 = time.time()
    for name, (truth, prov) in sorted(labels.items()):
        img = cv2.imread(str(folder / name))
        if img is None:
            continue
        crop = img
        if not a.crops:
            assert vehicle is not None and plate is not None
            dets = vehicle.detect(img, conf=0.3, classes=set(COCO_VEHICLES), agnostic=True)
            region = img
            if dets:
                d = max(dets, key=lambda d: d.w * d.h)
                region = img[int(d.y1):int(d.y2), int(d.x1):int(d.x2)]
            pb = plate.detect(region)
            if pb is not None:
                crop = pb.crop(region)
            else:
                pb = plate.detect(img)
                crop = pb.crop(img) if pb else None
        if crop is None or crop.size == 0:
            rows.append([name, truth, prov, "", "", 0.0, "ไม่พบป้าย"])
            continue
        r = reader.read(crop).parsed
        ok = "ถูก" if r.norm == truth else "ผิด"
        rows.append([name, truth, prov, r.norm, r.province or "", round(r.confidence, 3), ok])
    n = len(rows)
    plate_ok = sum(1 for r in rows if r[6] == "ถูก")
    prov_ok = sum(1 for r in rows if r[2] and r[4] == r[2])
    prov_n = sum(1 for r in rows if r[2])
    found = sum(1 for r in rows if r[6] != "ไม่พบป้าย")
    print(f"ภาพ {n} · พบป้าย {found} ({100 * found / n:.1f}%) · อ่านทะเบียนถูก {plate_ok} ({100 * plate_ok / n:.1f}%)"
          + (f" · จังหวัดถูก {prov_ok}/{prov_n} ({100 * prov_ok / max(1, prov_n):.1f}%)" if prov_n else "")
          + f" · {1000 * (time.time() - t0) / n:.0f} ms/ภาพ")
    for r in rows:
        if r[6] != "ถูก":
            print("  ", r)
    if a.report:
        with open(a.report, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ไฟล์", "เฉลย", "จังหวัด(เฉลย)", "อ่านได้", "จังหวัด(อ่านได้)", "ความมั่นใจ", "ผล"])
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
