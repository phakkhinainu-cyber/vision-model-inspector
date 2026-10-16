"""ดาวน์โหลดไฟล์ที่ไม่มีในสำเนาซอร์สบน Google Drive จาก GitHub

สำเนาใน Google Drive เก็บเฉพาะไฟล์ข้อความที่เขียนเอง ส่วนไฟล์ด้านล่างนี้ (ฟอนต์ ไอคอน วิดีโอตัวอย่าง ภาพหน้าจอ
package-lock.json ที่มีค่า hash ยาว ๆ, LICENSE ฉบับเต็ม, prompt ต้นฉบับ) ให้ดาวน์โหลดด้วยสคริปต์นี้ก่อน build หรือรันโปรแกรม
(สคริปต์จะสร้างไฟล์ __init__.py ที่ว่างเปล่าให้ด้วย เพราะ Google Drive เก็บไฟล์ว่างไม่ได้)

  python tools/fetch_assets.py              # ดาวน์โหลดไฟล์ที่ยังไม่มี
  python tools/fetch_assets.py --models     # + ไฟล์โมเดล ONNX (เรียก tools/fetch_models.py)
  python tools/fetch_assets.py --ref <branch/tag/commit> --force

ทางที่ง่ายกว่า: git clone https://github.com/phakkhinainu-cyber/vision-model-inspector (มีทุกไฟล์อยู่แล้ว)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "phakkhinainu-cyber/vision-model-inspector"
ROOT = Path(__file__).resolve().parents[1]  # โฟลเดอร์ lpr/

ASSETS = [
    "LICENSE",
    "frontend/package-lock.json",
    "docs/prompt-แบบ4.md",
    "backend/lpr/resources/fonts/Sarabun-Regular.ttf",
    "backend/lpr/resources/fonts/Sarabun-Bold.ttf",
    "backend/lpr/resources/icon.png",
    "frontend/public/icons/apple-touch-icon.png",
    "frontend/public/icons/favicon.png",
    "frontend/public/icons/icon-192.png",
    "frontend/public/icons/icon-512.png",
    "frontend/public/icons/maskable-512.png",
    "packaging/app.ico",
    "demo/demo.mp4",
    "docs/screenshots/desktop-camera-editor.png",
    "docs/screenshots/desktop-cameras.png",
    "docs/screenshots/desktop-inside.png",
    "docs/screenshots/desktop-logbook.png",
    "docs/screenshots/desktop-reports.png",
    "docs/screenshots/desktop-review.png",
    "docs/screenshots/desktop-settings.png",
    "docs/screenshots/desktop-vehicles.png",
    "docs/screenshots/login.png",
    "docs/screenshots/mobile-detail.png",
    "docs/screenshots/mobile-inside.png",
    "docs/screenshots/mobile-logbook.png",
    "docs/screenshots/tablet-logbook.png",
]

# ไฟล์ว่าง (Google Drive ไม่รับไฟล์ขนาด 0 byte)
EMPTY = [
    "backend/lpr/camera/__init__.py",
    "backend/lpr/events/__init__.py",
    "backend/lpr/vision/__init__.py",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="lpr-latest", help="branch / tag / commit ที่จะดาวน์โหลด (ค่าเริ่มต้น lpr-latest)")
    ap.add_argument("--force", action="store_true", help="ดาวน์โหลดทับไฟล์ที่มีอยู่แล้ว")
    ap.add_argument("--models", action="store_true", help="ดาวน์โหลดไฟล์โมเดลด้วย")
    a = ap.parse_args()
    ok = missing = skipped = 0
    for rel in EMPTY:
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / rel).touch(exist_ok=True)
    for rel in ASSETS:
        dst = ROOT / rel
        if dst.exists() and dst.stat().st_size > 0 and not a.force:
            skipped += 1
            continue
        url = f"https://raw.githubusercontent.com/{REPO}/{urllib.parse.quote(a.ref)}/lpr/{urllib.parse.quote(rel)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "lpr-fetch-assets"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {rel}: {e}")
            missing += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        print(f"  ✓ {rel} ({len(data):,} bytes)")
        ok += 1
    print(f"ดาวน์โหลด {ok} ไฟล์, มีอยู่แล้ว {skipped} ไฟล์" + (f", ไม่สำเร็จ {missing} ไฟล์" if missing else ""))
    if a.models:
        code = subprocess.call([sys.executable, str(ROOT / "tools" / "fetch_models.py")])
        if code:
            return code
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
