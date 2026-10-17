"""แปลงผังใน docs/diagrams/*.html เป็นรูป PNG (ความละเอียด 2 เท่า) ด้วย Edge/Chrome ที่มีในเครื่อง

  python tools/render_diagrams.py                  # ทุกไฟล์ใน docs/diagrams/
  python tools/render_diagrams.py docs/diagrams/roadmap.html

ขนาดหน้ากำหนดใน <meta name="render-size" content="1600x1720"> ของแต่ละไฟล์ (ส่วนที่ว่างด้านล่างจะถูกตัดออก)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_manual_pdf import DOCS, find_chrome  # noqa: E402


def trim_bottom(png: Path, margin: int = 72) -> None:
    from PIL import Image, ImageChops

    im = Image.open(png).convert("RGB")
    bbox = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
    if bbox and bbox[3] + margin < im.height:
        im.crop((0, 0, im.width, bbox[3] + margin)).save(png, optimize=True)


def render(src: Path, chrome: str, scale: int) -> Path:
    m = re.search(r'name="render-size" content="(\d+)x(\d+)"', src.read_text("utf-8"))
    w, h = (int(m.group(1)), int(m.group(2))) if m else (1600, 1200)
    out = src.with_suffix(".png")
    with tempfile.TemporaryDirectory(prefix="lpr-diagram-", ignore_cleanup_errors=True) as td:
        cmd = [chrome, "--headless", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
               "--allow-file-access-from-files", "--default-background-color=ffffffff", "--virtual-time-budget=8000",
               f"--force-device-scale-factor={scale}", f"--window-size={w},{h}", f"--user-data-dir={Path(td) / 'p'}",
               f"--screenshot={out}", src.resolve().as_uri()]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not out.exists():
        print(r.stdout, r.stderr, sep="\n")
        sys.exit(f"สร้างรูปจาก {src.name} ไม่สำเร็จ")
    trim_bottom(out, margin=36 * scale)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--chrome")
    ap.add_argument("--scale", type=int, default=2)
    a = ap.parse_args()
    files = [Path(f) for f in a.files] or sorted((DOCS / "diagrams").glob("*.html"))
    chrome = find_chrome(a.chrome)
    for f in files:
        out = render(f, chrome, a.scale)
        print(f"สร้าง {out} ({out.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
