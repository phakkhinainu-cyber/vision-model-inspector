"""สร้างไอคอนของโปรแกรม (tray, PWA, Windows .ico) — python tools/make_icons.py"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "backend" / "lpr" / "resources" / "fonts" / "Sarabun-Bold.ttf"
INDIGO, WHITE, INK = (67, 56, 202), (255, 255, 255), (20, 26, 46)


def draw(size: int, maskable: bool = False) -> Image.Image:
    s = 4 * size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        d.rectangle([0, 0, s, s], fill=INDIGO)
        pad = int(s * 0.2)
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=INDIGO)
        pad = int(s * 0.12)
    # ป้ายทะเบียนสีขาว 2 บรรทัด
    pw = s - 2 * pad
    ph = int(pw * 0.62)
    x0, y0 = pad, (s - ph) // 2
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=int(pw * 0.09), fill=WHITE, outline=INK,
                        width=max(2, int(pw * 0.035)))
    f1 = ImageFont.truetype(str(FONT), int(ph * 0.5))
    f2 = ImageFont.truetype(str(FONT), int(ph * 0.24))
    for text, f, cy in (("LPR", f1, y0 + ph * 0.38), ("บ้าน", f2, y0 + ph * 0.77)):
        b = d.textbbox((0, 0), text, font=f)
        d.text((s / 2 - (b[2] - b[0]) / 2 - b[0], cy - (b[3] - b[1]) / 2 - b[1]), text, font=f, fill=INK)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    pub = ROOT / "frontend" / "public" / "icons"
    pub.mkdir(parents=True, exist_ok=True)
    draw(192).save(pub / "icon-192.png")
    draw(512).save(pub / "icon-512.png")
    draw(512, maskable=True).save(pub / "maskable-512.png")
    draw(180, maskable=True).convert("RGB").save(pub / "apple-touch-icon.png")
    draw(64).save(pub / "favicon.png")
    draw(256).save(ROOT / "backend" / "lpr" / "resources" / "icon.png")
    big = draw(256)
    big.save(ROOT / "packaging" / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                                     (256, 256)])
    print("icons written")


if __name__ == "__main__":
    main()
