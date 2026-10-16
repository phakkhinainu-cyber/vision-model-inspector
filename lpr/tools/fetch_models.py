"""ดาวน์โหลดไฟล์โมเดล ONNX (จาก release "lpr-models-v1") มาไว้ที่โฟลเดอร์ models/ และตรวจ sha256

python tools/fetch_models.py [--base URL] [--dest models]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/phakkhinainu-cyber/vision-model-inspector/releases/download/lpr-models-v1"
EXTRA = ["th_PP-OCRv5_mobile_rec.dict.txt", "vehicle_yolo11n.names.json", "plate_yolo.names.json"]


def fetch(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "lpr-fetch"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--dest", default=str(Path(__file__).resolve().parents[1] / "models"))
    a = ap.parse_args()
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    fetch(f"{a.base}/manifest.json", dest / "manifest.json")
    man = json.loads((dest / "manifest.json").read_text("utf-8"))
    files = [(v["file"], v.get("sha256")) for v in man.values() if isinstance(v, dict) and "file" in v]
    files += [(x, None) for x in EXTRA]
    ok = True
    for name, digest in files:
        p = dest / name
        if p.exists() and (digest is None or sha256(p) == digest):
            print("มีอยู่แล้ว", name)
            continue
        print("ดาวน์โหลด", name)
        fetch(f"{a.base}/{name}", p)
        if digest and sha256(p) != digest:
            print("  ✗ sha256 ไม่ตรง", name)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
