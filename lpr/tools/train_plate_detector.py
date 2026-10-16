"""Fine-tune โมเดลตรวจจับป้ายทะเบียน (YOLO) ด้วยภาพป้ายไทยของคุณ แล้วส่งออกเป็น ONNX ให้โปรแกรมใช้

ต้องติดตั้งเพิ่ม (เครื่องที่ใช้ฝึก ไม่ใช่เครื่องที่ติดตั้งโปรแกรม):
  pip install "ultralytics>=8.3,<8.4"     (มีการ์ด NVIDIA จะเร็วกว่ามาก)

ข้อมูล: โฟลเดอร์ frames/ จาก tools/collect_plates.py (ภาพ .jpg + กรอบ .txt แบบ YOLO) — ตรวจแก้กรอบด้วยโปรแกรมเช่น
LabelImg / CVAT / Label Studio (ส่งออกแบบ YOLO) ก่อนฝึก

python tools/train_plate_detector.py --data D:\\LPR\\dataset\\frames --epochs 60
ผลลัพธ์: models/plate_yolo.onnx (วางไว้ที่ <ที่เก็บข้อมูล>\\models\\ เพื่อให้โปรแกรมที่ติดตั้งแล้วใช้แทนตัวเดิม)
"""
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


def split_dataset(src: Path, work: Path, val_ratio: float = 0.15) -> Path:
    imgs = sorted(p for p in src.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.with_suffix(".txt").exists())
    if len(imgs) < 20:
        raise SystemExit(f"มีภาพที่ติดป้ายกำกับแล้วเพียง {len(imgs)} ภาพ ควรมีอย่างน้อย 200 ภาพ")
    random.Random(0).shuffle(imgs)
    n_val = max(1, int(len(imgs) * val_ratio))
    for split, items in (("val", imgs[:n_val]), ("train", imgs[n_val:])):
        for sub in ("images", "labels"):
            (work / sub / split).mkdir(parents=True, exist_ok=True)
        for p in items:
            shutil.copy(p, work / "images" / split / p.name)
            shutil.copy(p.with_suffix(".txt"), work / "labels" / split / (p.stem + ".txt"))
    yaml = work / "data.yaml"
    yaml.write_text(f"path: {work.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: license_plate\n", "utf-8")
    print(f"train {len(imgs) - n_val} / val {n_val} ภาพ")
    return yaml


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="โฟลเดอร์ภาพ + .txt แบบ YOLO")
    ap.add_argument("--base", default="", help="โมเดลตั้งต้น (.pt) เช่น license-plate-finetune-v1n.pt หรือ yolo11n.pt")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "models" / "plate_yolo.onnx"))
    a = ap.parse_args()
    from ultralytics import YOLO

    work = Path("work/plate_train")
    if work.exists():
        shutil.rmtree(work)
    yaml = split_dataset(Path(a.data), work)
    base = a.base or "yolo11n.pt"
    model = YOLO(base)
    model.train(data=str(yaml), epochs=a.epochs, imgsz=a.imgsz, batch=16, patience=15, project="work/runs", name="plate",
                exist_ok=True, degrees=5, perspective=0.0005, hsv_v=0.5, fliplr=0.0)
    best = Path("work/runs/plate/weights/best.pt")
    metrics = YOLO(str(best)).val(data=str(yaml))
    print("mAP50:", getattr(metrics.box, "map50", None))
    onnx = YOLO(str(best)).export(format="onnx", imgsz=a.imgsz, opset=12, simplify=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(onnx, a.out)
    print("บันทึกโมเดลที่", a.out)


if __name__ == "__main__":
    main()
