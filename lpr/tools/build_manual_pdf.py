"""สร้างคู่มือผู้ใช้ฉบับ PDF (docs/user-manual.pdf) จาก docs/user-manual.md + docs/mobile-setup.md

ใช้เบราว์เซอร์ตระกูล Chromium ที่มีในเครื่อง (Microsoft Edge / Google Chrome / Chromium) พิมพ์เป็น PDF
จึงจัดสระและวรรณยุกต์ไทยได้ถูกต้อง ฟอนต์ Sarabun และภาพหน้าจอฝังอยู่ในไฟล์ ไม่ต้องต่ออินเทอร์เน็ต

  pip install markdown-it-py
  python tools/build_manual_pdf.py                       # ได้ docs/user-manual.pdf
  python tools/build_manual_pdf.py --out คู่มือ.pdf --chrome "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
"""
from __future__ import annotations

import argparse
import base64
import glob
import html
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # โฟลเดอร์ lpr/
DOCS = ROOT / "docs"
FONTS = ROOT / "backend" / "lpr" / "resources" / "fonts"
GITHUB_DOCS = "https://github.com/phakkhinainu-cyber/vision-model-inspector/blob/lpr-latest/lpr/docs/"
DOWNLOAD = "https://github.com/phakkhinainu-cyber/vision-model-inspector/releases/download/lpr-latest/"
THAI_MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
               "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

# ภาพหน้าจอที่ไม่ได้อยู่ในเนื้อหาหลัก แสดงในภาคผนวก ก
GALLERY = [
    ("desktop-inside.png", "รถที่อยู่ในพื้นที่ตอนนี้ (คอมพิวเตอร์)"),
    ("desktop-vehicles.png", "ทะเบียนรถ: รถของบ้าน / ผู้มาเยือนประจำ / บัญชีดำ"),
    ("desktop-cameras.png", "หน้ากล้อง: สถานะและภาพสดของแต่ละกล้อง"),
    ("desktop-settings.png", "หน้าตั้งค่า"),
    ("tablet-logbook.png", "สมุดบันทึกบนแท็บเล็ต"),
]
GALLERY_PHONES = [
    ("mobile-logbook.png", "มือถือ: รายการเข้า-ออก"),
    ("mobile-inside.png", "มือถือ: รถในพื้นที่"),
    ("mobile-detail.png", "มือถือ: รายละเอียดเหตุการณ์"),
]


def b64(p: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def image_uri(p: Path, max_w: int = 1600) -> str:
    """ภาพหน้าจอ PNG → JPEG คุณภาพ 88 (ไฟล์ PDF เล็กลงมาก แต่ยังคมพอสำหรับอ่าน/พิมพ์)"""
    try:
        from PIL import Image

        im = Image.open(p).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88, optimize=True, progressive=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return b64(p, "image/png")


def render_md(text: str) -> str:
    from markdown_it import MarkdownIt

    return MarkdownIt("commonmark", {"html": True}).enable("table").render(text)


def fix_body(h: str, shift: int = 0) -> str:
    """ภาพ → data URI + คำบรรยาย, ลิงก์ .md → ภาคผนวก/GitHub, เลื่อนระดับหัวข้อ"""
    def img(m: re.Match[str]) -> str:
        attrs = m.group(1)
        src = re.search(r'src="([^"]+)"', attrs)
        alt = re.search(r'alt="([^"]*)"', attrs)
        if not src or src.group(1).startswith(("http:", "https:", "data:")):
            return m.group(0)
        uri = image_uri(DOCS / html.unescape(src.group(1)))
        phone = 'width="' in attrs
        cls = "phone" if phone else ("shot diagram" if "diagrams/" in src.group(1) else "shot")
        return f'<img class="{cls}" src="{uri}" alt="{alt.group(1) if alt else ""}">'

    h = re.sub(r"<img\s+([^>]*?)/?>", img, h)
    # ภาพเดี่ยวทั้งย่อหน้า → figure + คำบรรยาย
    h = re.sub(r'<p>\s*(<img class="shot[^"]*" src="[^"]+" alt="([^"]*)">)\s*</p>',
               lambda m: f'<figure>{m.group(1)}<figcaption>{m.group(2)}</figcaption></figure>', h)
    # ภาพมือถือหลายภาพในย่อหน้าเดียว → แถวภาพ
    h = re.sub(r'<p>\s*((?:<img class="phone"[^>]+>\s*)+)</p>',
               lambda m: '<figure class="row">' + "".join(
                   f'<div>{x}<figcaption>{re.search(r"alt=\"([^\"]*)\"", x).group(1)}</figcaption></div>'
                   for x in re.findall(r'<img class="phone"[^>]+>', m.group(1))) + "</figure>", h)

    def link(m: re.Match[str]) -> str:
        href, text = m.group(1), m.group(2)
        if href == "mobile-setup.md":
            return '<a href="#appendix-mobile">ภาคผนวก ข (ดูผ่านมือถือและนอกบ้าน)</a>'
        if re.match(r"^[\w-]+\.md(#.*)?$", href):
            return f'<a href="{GITHUB_DOCS}{href}">{text} (บน GitHub)</a>'
        return m.group(0)

    h = re.sub(r'<a href="([^"]+)">(.*?)</a>', link, h)
    if shift:
        h = re.sub(r"<(/?)h([1-5])", lambda m: f"<{m.group(1)}h{int(m.group(2)) + shift}", h)
    return h


def number_sections(h: str) -> tuple[str, list[tuple[str, str]]]:
    toc: list[tuple[str, str]] = []

    def sec(m: re.Match[str]) -> str:
        sid = f"sec-{len(toc) + 1}"
        toc.append((sid, re.sub(r"<[^>]+>", "", m.group(1))))
        return f'<h2 id="{sid}">{m.group(1)}</h2>'

    return re.sub(r"<h2>(.*?)</h2>", sec, h), toc


def thai_date(d: date) -> str:
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"


def version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "backend" / "lpr" / "__init__.py").read_text("utf-8"))
    return m.group(1) if m else "?"


def build_html() -> str:
    manual = (DOCS / "user-manual.md").read_text("utf-8")
    title_m = re.match(r"#\s+(.+)\n", manual)
    title = title_m.group(1).strip() if title_m else "คู่มือผู้ใช้ LPR บ้าน"
    manual = manual[title_m.end():] if title_m else manual
    manual = manual[manual.find("\n## ") + 1:] if "\n## " in manual else manual  # ข้อความก่อนหัวข้อ 1 อยู่บนปกแล้ว
    body, toc = number_sections(fix_body(render_md(manual)))

    mobile = (DOCS / "mobile-setup.md").read_text("utf-8")
    mt = re.match(r"#\s+(.+)\n", mobile)
    mobile_title = mt.group(1).strip() if mt else "ดูผ่านมือถือ"
    mobile_body = fix_body(render_md(mobile[mt.end():] if mt else mobile), shift=1)

    gallery = "".join(f'<figure><img class="shot" src="{image_uri(DOCS / "screenshots" / f)}" alt="{c}">'
                      f"<figcaption>{c}</figcaption></figure>" for f, c in GALLERY)
    gallery += '<figure class="row phones3">' + "".join(
        f'<div><img class="phone" src="{image_uri(DOCS / "screenshots" / f, 900)}" alt="{c}">'
        f"<figcaption>{c}</figcaption></div>" for f, c in GALLERY_PHONES) + "</figure>"

    toc_html = "".join(f'<li><a href="#{sid}">{html.escape(t)}</a></li>' for sid, t in toc)
    toc_html += ('<li class="app"><a href="#appendix-gallery">ภาคผนวก ก: ภาพหน้าจออื่น ๆ</a></li>'
                 f'<li class="app"><a href="#appendix-mobile">ภาคผนวก ข: {html.escape(mobile_title)}</a></li>')

    mono = ""
    for f in sorted(glob.glob(str(ROOT / "frontend/node_modules/@fontsource/jetbrains-mono/files/"
                                      "jetbrains-mono-latin-400-normal.woff2"))):
        mono = f"@font-face{{font-family:'JB Mono';src:url({b64(Path(f), 'font/woff2')}) format('woff2');}}"
    ver = version()
    hero = image_uri(DOCS / "screenshots" / "desktop-logbook.png")
    icon = b64(ROOT / "backend" / "lpr" / "resources" / "icon.png", "image/png")
    css = f"""
@font-face{{font-family:'Sarabun';font-weight:400;src:url({b64(FONTS / 'Sarabun-Regular.ttf', 'font/ttf')}) format('truetype');}}
@font-face{{font-family:'Sarabun';font-weight:700;src:url({b64(FONTS / 'Sarabun-Bold.ttf', 'font/ttf')}) format('truetype');}}
{mono}
@page {{ size: A4; margin: 18mm 17mm 20mm 17mm;
  @bottom-left {{ content: "{title}"; font: 8.5pt Sarabun; color: #8a8f98; }}
  @bottom-right {{ content: "หน้า " counter(page) " / " counter(pages); font: 8.5pt Sarabun; color: #8a8f98; }} }}
@page :first {{ margin: 0; @bottom-left {{ content: none; }} @bottom-right {{ content: none; }} }}
:root {{ --ink:#1d2433; --muted:#5b6475; --line:#d9dee7; --accent:#0f6e5a; --accent-bg:#e8f4f0; --code-bg:#f3f5f8; }}
* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ font-family: Sarabun, sans-serif; font-size: 11.5pt; line-height: 1.66; color: var(--ink); margin: 0; }}
h2, h3, h4 {{ line-height: 1.55; padding-top: 1.5mm; break-after: avoid; }}  /* เผื่อที่ให้วรรณยุกต์ ไม่ล้นไปหน้าก่อน */
h2 {{ font-size: 18pt; color: var(--accent); margin: 0 0 4mm; padding-bottom: 2mm; border-bottom: 1.5pt solid var(--accent); }}
.part {{ break-before: page; }}
h3 {{ font-size: 13.5pt; margin: 6mm 0 2mm; }}
h4 {{ font-size: 12pt; margin: 5mm 0 2mm; }}
/* padding บนย่อหน้า/รายการ: สระบนซ้อนวรรณยุกต์ (เช่น นี้) ของบรรทัดแรกในหน้าใหม่จะได้ไม่ล้นไปค้างท้ายหน้าก่อน */
p {{ margin: 0 0 2mm; padding-top: .25em; }}
ul, ol {{ margin: 0 0 3mm; padding-left: 7mm; }}
li {{ margin-bottom: .6mm; padding-top: .25em; }}
li > ul, li > ol {{ margin-top: 1.2mm; }}
a {{ color: var(--accent); text-decoration: none; }}
strong {{ font-weight: 700; }}
code {{ font-family: 'JB Mono', Consolas, 'Courier New', Sarabun, monospace; font-size: 9.5pt; background: var(--code-bg);
  padding: .3mm 1.2mm; border-radius: 1mm; word-break: break-word; }}
pre {{ background: var(--code-bg); border: .5pt solid var(--line); border-radius: 2mm; padding: 3mm 4mm; white-space: pre-wrap;
  word-break: break-all; break-inside: avoid; margin: 0 0 3mm; }}
pre code {{ background: none; padding: 0; font-size: 9pt; }}
blockquote {{ margin: 0 0 3mm; padding: 2.5mm 4mm; background: var(--accent-bg); border-left: 1.2mm solid var(--accent);
  border-radius: 0 2mm 2mm 0; }}
blockquote p:last-child {{ margin: 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 1mm 0 4mm; font-size: 10.5pt; break-inside: auto; }}
th, td {{ border: .5pt solid var(--line); padding: 2mm 2.5mm 1.6mm; text-align: left; vertical-align: top; }}
th {{ background: var(--code-bg); font-weight: 700; }}
tr {{ break-inside: avoid; }}
figure {{ margin: 2mm 0 5mm; text-align: center; break-inside: avoid; }}
img.shot {{ max-width: 100%; max-height: 120mm; border: .5pt solid var(--line); border-radius: 2mm; }}
img.diagram {{ max-height: 235mm; border: none; }}
figure.row {{ display: flex; justify-content: center; gap: 6mm; align-items: flex-start; }}
figure.row > div {{ width: 46%; }}
figure.phones3 > div {{ width: 31%; }}
img.phone {{ width: 100%; max-height: 150mm; object-fit: contain; object-position: top; border: .5pt solid var(--line);
  border-radius: 2mm; }}
figcaption {{ font-size: 9.5pt; color: var(--muted); margin-top: 1.5mm; }}
.cover {{ height: 297mm; padding: 26mm 20mm 18mm; display: flex; flex-direction: column; break-after: page;
  background: linear-gradient(180deg, var(--accent-bg) 0, #fff 62%); }}
.cover .brand {{ display: flex; align-items: center; gap: 5mm; }}
.cover .brand img {{ width: 22mm; height: 22mm; border-radius: 5mm; }}
.cover .brand span {{ font-size: 13pt; color: var(--muted); }}
.cover h1 {{ font-size: 34pt; line-height: 1.2; margin: 16mm 0 3mm; color: var(--ink); }}
.cover .sub {{ font-size: 15pt; color: var(--muted); margin: 0 0 12mm; }}
.cover .hero {{ width: 100%; border: .5pt solid var(--line); border-radius: 3mm; box-shadow: 0 2mm 6mm rgba(0,0,0,.12); }}
.cover .meta {{ margin-top: auto; font-size: 10.5pt; color: var(--muted); border-top: .5pt solid var(--line); padding-top: 4mm; }}
.toc h2 {{ break-before: auto; }}
.toc ol {{ list-style: none; padding: 0; font-size: 13pt; }}
.toc li {{ padding: 2mm 0; border-bottom: .5pt dotted var(--line); margin: 0; }}
.toc li.app {{ color: var(--muted); }}
.intro {{ font-size: 12pt; }}
"""
    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{css}</style></head><body>
<div class="cover">
  <div class="brand"><img src="{icon}" alt=""><span>LPR บ้าน · ระบบตรวจป้ายทะเบียนรถสำหรับบ้านพัก</span></div>
  <h1>{html.escape(title)}</h1>
  <p class="sub">ติดตั้ง ตั้งค่ากล้อง ใช้งานสมุดบันทึกเข้า-ออก (แบบ 4) และดูผ่านมือถือ</p>
  <img class="hero" src="{hero}" alt="หน้าจอสมุดบันทึกเข้า-ออก">
  <div class="meta">เวอร์ชัน {ver} · ปรับปรุงล่าสุด {thai_date(date.today())}<br>
  ดาวน์โหลดโปรแกรมและคู่มือฉบับล่าสุด: {DOWNLOAD}</div>
</div>
<section class="toc"><h2>สารบัญ</h2><ol>{toc_html}</ol></section>
<section class="chapter part">{body}</section>
<section class="part" id="appendix-gallery"><h2>ภาคผนวก ก: ภาพหน้าจออื่น ๆ</h2>{gallery}</section>
<section class="part" id="appendix-mobile"><h2>ภาคผนวก ข: {html.escape(mobile_title)}</h2>{mobile_body}</section>
</body></html>"""


def find_chrome(explicit: str | None) -> str:
    cands: list[str] = [explicit] if explicit else []
    if os.environ.get("CHROME"):
        cands.append(os.environ["CHROME"])
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     os.environ.get("PROGRAMFILES", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            cands += [rf"{base}\Microsoft\Edge\Application\msedge.exe", rf"{base}\Google\Chrome\Application\chrome.exe"]
    elif sys.platform == "darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "chrome"):
        if shutil.which(name):
            cands.append(shutil.which(name) or "")
    cands += sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"), reverse=True)
    for c in cands:
        if c and Path(c).exists():
            return c
    sys.exit("ไม่พบ Microsoft Edge / Google Chrome / Chromium — ระบุด้วย --chrome PATH")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DOCS / "user-manual.pdf"))
    ap.add_argument("--chrome", help="ที่อยู่ของ msedge.exe / chrome.exe / chromium")
    ap.add_argument("--html", help="บันทึกไฟล์ HTML ที่ใช้สร้าง PDF ไว้ดูด้วย")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    page = build_html()
    if a.html:
        Path(a.html).write_text(page, "utf-8")
    chrome = find_chrome(a.chrome)
    with tempfile.TemporaryDirectory(prefix="lpr-manual-", ignore_cleanup_errors=True) as td:
        src = Path(td) / "manual.html"
        src.write_text(page, "utf-8")
        cmd = [chrome, "--headless", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
               "--print-to-pdf-no-header", "--virtual-time-budget=15000", f"--user-data-dir={Path(td) / 'profile'}",
               f"--print-to-pdf={out}", src.as_uri()]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out.exists() or out.stat().st_size < 10_000:
        print(r.stdout, r.stderr, sep="\n")
        sys.exit("สร้าง PDF ไม่สำเร็จ")
    print(f"สร้าง {out} ({out.stat().st_size / 1e6:.1f} MB) ด้วย {Path(chrome).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
