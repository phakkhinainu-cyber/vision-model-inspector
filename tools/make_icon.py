"""Generate packaging/app.ico (purple rounded square with a white eye)."""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def draw(size):
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 5, fill=(91, 63, 217, 255))
    cx, cy = s / 2, s / 2
    w, h = s * 0.74, s * 0.44
    d.ellipse([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], fill=(255, 255, 255, 255))
    r = s * 0.17
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(31, 43, 77, 255))
    r2 = s * 0.06
    d.ellipse([cx - r2 + r * 0.35, cy - r2 - r * 0.35, cx + r2 + r * 0.35, cy + r2 - r * 0.35],
              fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.LANCZOS)


def main():
    out = os.path.join(ROOT, "packaging", "app.ico")
    big = draw(256)
    big.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(os.path.join(ROOT, "packaging", "app.png"))
    print(out)


if __name__ == "__main__":
    main()
