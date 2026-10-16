"""เตรียมข้อมูลฝึก OCR (PaddleOCR rec) จากภาพป้ายที่เก็บไว้ + labels.tsv ที่ตรวจแก้แล้ว

แต่ละป้ายจะถูกแยกเป็นบรรทัด (บรรทัดทะเบียน และบรรทัดจังหวัด) แล้วเขียนไฟล์ป้ายกำกับรูปแบบ PaddleOCR:
  rec/images/xxx_0.jpg  + rec/train.txt, rec/val.txt   ("images/xxx_0.jpg<TAB>1กข 4521")

python tools/prepare_ocr_dataset.py D:\\LPR\\dataset --out work/ocr_data
จากนั้นฝึกด้วย PaddleOCR ตาม docs/fine-tune.md
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lpr.plates.parser import format_display, normalize_plate_text  # noqa: E402
from lpr.vision.ocr.textdet import projection_lines  # noqa: E402
from lpr.vision.preprocess import prepare_plate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", help="โฟลเดอร์ที่มี labels.tsv และ plates/")
    ap.add_argument("--out", default="work/ocr_data")
    ap.add_argument("--val", type=float, default=0.1)
    a = ap.parse_args()
    src, out = Path(a.dataset), Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    rows = []
    for line in (src / "labels.tsv").read_text("utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[1].strip():
            continue
        norm, _, valid = normalize_plate_text(parts[1])
        if not valid:
            continue
        img = cv2.imread(str(src / parts[0]))
        if img is None:
            continue
        proc = prepare_plate(img)
        boxes = projection_lines(proc)
        texts = [format_display(norm)] + ([parts[2].strip()] if len(parts) > 2 and parts[2].strip() else [])
        if len(boxes) < len(texts):
            continue
        stem = Path(parts[0]).stem
        for k, (box, text) in enumerate(zip(boxes, texts)):
            x1, y1, x2, y2 = box
            name = f"{stem}_{k}.jpg"
            cv2.imwrite(str(out / "images" / name), proc[y1:y2, x1:x2])
            rows.append(f"images/{name}\t{text}")
    random.Random(0).shuffle(rows)
    n_val = max(1, int(len(rows) * a.val))
    (out / "val.txt").write_text("\n".join(rows[:n_val]) + "\n", "utf-8")
    (out / "train.txt").write_text("\n".join(rows[n_val:]) + "\n", "utf-8")
    print(f"บรรทัดข้อความ {len(rows)} (train {len(rows) - n_val} / val {n_val}) ที่ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
