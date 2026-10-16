"""สร้างภาพป้ายทะเบียนไทยจำลอง (ใช้ทดสอบความแม่นยำ, ทำวิดีโอตัวอย่าง และทดสอบอัตโนมัติ)

python tools/synth_plates.py --out work/synth --n 50
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lpr.plates.provinces import PROVINCES  # noqa: E402

FONT = ROOT / "backend" / "lpr" / "resources" / "fonts" / "Sarabun-Bold.ttf"
LETTERS = "กขคงจฉชซญฎฐฒณดตถทธนบปผพฟภมยรลวศษสหฬอฮ"
STYLES = {
    "white_black": ((255, 255, 255), (20, 20, 20)),
    "white_green": ((255, 255, 255), (20, 120, 40)),
    "white_blue": ((255, 255, 255), (30, 50, 160)),
    "yellow_black": ((245, 200, 30), (20, 20, 20)),
    "red": ((210, 30, 35), (20, 20, 20)),
}


def random_plate(rng: random.Random, kind: str = "car") -> tuple[str, str, str]:
    """คืน (ข้อความบรรทัดบน, plate_norm, จังหวัด)"""
    prov = rng.choice(PROVINCES)
    if kind == "public":
        a, b = rng.randint(10, 99), rng.randint(1000, 9999)
        return f"{a}-{b}", f"{a}{b}", prov
    prefix = str(rng.randint(1, 9)) if rng.random() < 0.5 else ""
    letters = "".join(rng.choice(LETTERS) for _ in range(rng.choice([2, 2, 1]) if prefix else 2))
    num = str(rng.randint(1, 9999))
    return f"{prefix}{letters} {num}", f"{prefix}{letters}{num}", prov


def render_plate(top: str, province: str, style: str = "white_black", width: int = 340,
                 motorcycle: bool = False, bottom: str = "") -> np.ndarray:
    bg, fg = STYLES[style]
    if motorcycle:
        w, h = int(width * 0.55), int(width * 0.38)
    else:
        w, h = width, int(width * 15 / 34)
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([3, 3, w - 4, h - 4], radius=max(4, w // 40), outline=fg, width=max(2, w // 110))

    def fit(text: str, max_w: float, max_h: float) -> ImageFont.FreeTypeFont:
        size = int(max_h)
        while size > 8:
            f = ImageFont.truetype(str(FONT), size)
            b = d.textbbox((0, 0), text, font=f)
            if b[2] - b[0] <= max_w and b[3] - b[1] <= max_h:
                return f
            size -= 2
        return ImageFont.truetype(str(FONT), 8)

    def center(text: str, y0: float, y1: float, max_w: float) -> None:
        f = fit(text, max_w, (y1 - y0) * 0.95)
        b = d.textbbox((0, 0), text, font=f)
        x = (w - (b[2] - b[0])) / 2 - b[0]
        y = y0 + ((y1 - y0) - (b[3] - b[1])) / 2 - b[1]
        d.text((x, y), text, font=f, fill=fg)

    if motorcycle:
        center(top, h * 0.06, h * 0.40, w * 0.8)
        center(province, h * 0.40, h * 0.62, w * 0.85)
        center(bottom, h * 0.60, h * 0.95, w * 0.7)
    else:
        center(top, h * 0.07, h * 0.66, w * 0.86)
        center(province, h * 0.64, h * 0.93, w * 0.8)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def degrade(img: np.ndarray, rng: random.Random, strength: float = 1.0) -> np.ndarray:
    """เพิ่มความเบลอ/สัญญาณรบกวน/มุมเอียงเล็กน้อย ให้เหมือนภาพจากกล้อง"""
    h, w = img.shape[:2]
    ang = rng.uniform(-6, 6) * strength
    m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
    k = rng.choice([1, 3, 3, 5]) if strength > 0.5 else 1
    if k > 1:
        img = cv2.GaussianBlur(img, (k, k), 0)
    noise = np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, 6 * strength, img.shape)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    q = int(rng.uniform(55, 90))
    ok, b = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return cv2.imdecode(b, cv2.IMREAD_COLOR)


def paste_plate(scene: np.ndarray, plate: np.ndarray, box_xywh: list[float]) -> np.ndarray:
    x, y, w, h = [int(round(v)) for v in box_xywh]
    out = scene.copy()
    H, W = out.shape[:2]
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    if w < 10 or h < 5:
        return out
    ph = int(w * plate.shape[0] / plate.shape[1])
    cy = y + h // 2
    y0 = max(0, cy - ph // 2)
    ph = min(ph, H - y0)
    out[y0:y0 + ph, x:x + w] = cv2.resize(plate, (w, ph), interpolation=cv2.INTER_AREA)[:ph]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="work/synth")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    labels = {}
    for i in range(a.n):
        kind = "public" if rng.random() < 0.15 else "car"
        style = rng.choice(list(STYLES)) if kind == "car" else "yellow_black"
        top, norm, prov = random_plate(rng, kind)
        img = degrade(render_plate(top, prov, style, width=rng.randint(140, 360)), rng)
        name = f"plate_{i:03d}.jpg"
        cv2.imwrite(str(out / name), img)
        labels[name] = {"plate_norm": norm, "province": prov, "style": style}
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1), "utf-8")
    print("wrote", a.n, "plates to", out)


if __name__ == "__main__":
    main()
