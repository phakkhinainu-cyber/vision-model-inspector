"""Build the Thai user manual (PDF) from real screenshots.

Usage: python tools/build_manual.py <screenshots_dir> <fonts_dir> <out.pdf> [facts.json]
Rendering uses Chromium (Playwright) so Thai text is shaped correctly.
"""
from __future__ import annotations

import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from vmi import __version__  # noqa: E402


def uri(p):
    from pathlib import Path
    return Path(p).resolve().as_uri()


CALLOUTS = [
    ("open", "เปิดโมเดล", "เลือกไฟล์ .pt (Ultralytics YOLOv8/YOLO11) หรือ .onnx"),
    ("model", "โมเดลปัจจุบัน", "ชื่อโมเดลที่เปิดอยู่ และรายการโมเดลที่เปิดล่าสุด"),
    ("mode", "แหล่งข้อมูล", "กล้อง / วิดีโอ / รูปภาพ / โฟลเดอร์ภาพ"),
    ("camera", "เลือกกล้องหรือไฟล์", "รายการกล้อง ปุ่มรีเฟรช และปุ่มตั้งค่ากล้อง (หรือช่องเลือกไฟล์)"),
    ("start", "เริ่ม / หยุด", "เริ่มรับภาพและตรวจจับ, หยุดแหล่งภาพ (วิดีโอหยุดชั่วคราวได้)"),
    ("capture", "จับภาพ", "บันทึก snapshot พร้อมผลตรวจจับของเฟรมนั้น (Space)"),
    ("gradcam", "วิเคราะห์", "คำนวณ Grad-CAM ของวัตถุที่เลือก (Ctrl+G)"),
    ("export", "ส่งออก", "บันทึกภาพ CSV และ metadata JSON (Ctrl+E)"),
    ("live", "ภาพสด", "ภาพจากแหล่งภาพพร้อมกรอบของเฟรมเดียวกัน ชื่อแหล่งภาพ และความละเอียดจริง"),
    ("strip", "ภาพที่บันทึก", "snapshot เรียงตามลำดับพร้อมหมายเลขและเวลา คลิกขวาเพื่อเปิดดู/ลบ"),
    ("info", "ข้อความแจ้ง/สรุปโมเดล", "ข้อความเตือนเรื่อง Grad-CAM และสรุปโมเดลที่เปิด"),
    ("det_card", "ผลการตรวจ (ซ้าย)", "ภาพที่จับไว้พร้อมกรอบ ซูม/เลื่อนได้ คลิกกรอบเพื่อเลือกวัตถุ"),
    ("gc_card", "Grad-CAM (ขวา)", "แผนที่สีของวัตถุที่เลือกจาก snapshot เดียวกัน"),
    ("settings", "แผงตั้งค่า", "วัตถุเป้าหมาย ชั้นเป้าหมาย ความทึบ เกณฑ์ต่าง ๆ ขนาด input อุปกรณ์ประมวลผล"),
    ("table", "ตารางวัตถุที่ตรวจพบ", "ลำดับ รหัสคลาส ชื่อคลาส ความมั่นใจ และปุ่มเลือก"),
    ("detail", "รายละเอียดวัตถุ", "ภาพย่อ ประเภท ความมั่นใจ กรอบ (x, y, w, h) ขนาดภาพ โมเดล"),
    ("status", "แถบสถานะ", "สถานะงาน แหล่งภาพ device, Capture FPS, Inference FPS, จำนวนวัตถุในเฟรม, เวลา"),
]


def figure(shots, name, caption, cls=""):
    p = os.path.join(shots, name)
    if not os.path.exists(p):
        return f'<div class="missing">[ไม่พบภาพ {html.escape(name)}]</div>'
    return (f'<figure class="{cls}"><img src="{uri(p)}"/>'
            f'<figcaption>{caption}</figcaption></figure>')


def annotated_main(shots, geo):
    p = os.path.join(shots, "01_main.png")
    if not geo or not os.path.exists(p):
        return figure(shots, "01_main.png", "หน้าจอหลัก")
    W, H = geo["_window"][2], geo["_window"][3]
    marks = []
    for i, (key, _t, _d) in enumerate(CALLOUTS, 1):
        if key not in geo:
            continue
        x, y, w, h = geo[key]
        cx = (x + min(w, 44) * 0.5 if w < 300 else x + 18) / W * 100
        cy = (y + min(h, 30) * 0.5 if h < 60 else y + 18) / H * 100
        marks.append(f'<span class="mark" style="left:{cx:.2f}%;top:{cy:.2f}%">{i}</span>')
    return (f'<figure class="annot"><div class="annot-wrap"><img src="{uri(p)}"/>{"".join(marks)}</div>'
            '<figcaption>รูปที่ 1 หน้าจอหลัก (UI แบบ C) ขณะวิเคราะห์ Grad-CAM — ภาพจากโปรแกรมจริง '
            'ใช้โมเดล yolov8n.pt บน CPU</figcaption></figure>')


def build_html(shots, fonts, facts):
    geo = facts.get("geometry_1600")
    f = lambda n: uri(os.path.join(fonts, n))  # noqa: E731
    callout_rows = "".join(
        f"<tr><td class='num'><span class='dot'>{i}</span></td><td><b>{t}</b></td><td>{d}</td></tr>"
        for i, (_k, t, d) in enumerate(CALLOUTS, 1))
    gc = facts.get("gradcam") or {}
    perf = facts.get("perf", {})
    css = f"""
@font-face {{ font-family: Plex; src: url('{f("IBMPlexSansThai-Regular.ttf")}'); font-weight: 400; }}
@font-face {{ font-family: Plex; src: url('{f("IBMPlexSansThai-Medium.ttf")}'); font-weight: 500; }}
@font-face {{ font-family: Plex; src: url('{f("IBMPlexSansThai-SemiBold.ttf")}'); font-weight: 600; }}
@font-face {{ font-family: Plex; src: url('{f("IBMPlexSansThai-Bold.ttf")}'); font-weight: 700; }}
@page {{ size: A4; margin: 18mm 16mm 18mm 16mm; }}
@page :first {{ margin: 0; }}
:root {{ --navy:#1F2B4D; --purple:#5B3FD9; --purple2:#7350EC; --soft:#ECE8FD; --muted:#5F6880;
        --border:#D8DDE8; --bg:#EEF1F6; --info:#E7F0FD; --warn:#FFF4DD; --green:#23964A; }}
* {{ box-sizing: border-box; }}
body {{ font-family: Plex, sans-serif; color: #1E2433; font-size: 10.5pt; line-height: 1.62; margin: 0; }}
h1 {{ font-size: 19pt; color: var(--navy); margin: 0 0 6mm; padding-bottom: 2.5mm;
      border-bottom: 2.5px solid var(--purple); break-after: avoid; }}
h1 .n {{ color: var(--purple); margin-right: 3mm; }}
h2 {{ font-size: 13pt; color: var(--purple); margin: 6mm 0 2mm; break-after: avoid; }}
h3 {{ font-size: 11pt; margin: 4mm 0 1mm; break-after: avoid; }}
p {{ margin: 0 0 2.6mm; }}
section {{ break-before: page; }}
figure {{ margin: 3mm 0 5mm; break-inside: avoid; }}
figure img {{ width: 100%; border: 1px solid var(--border); border-radius: 6px; display: block; }}
figure.half img {{ width: 78%; margin: 0 auto; }}
figure.small img {{ width: 62%; margin: 0 auto; }}
figcaption {{ font-size: 8.8pt; color: var(--muted); text-align: center; margin-top: 1.6mm; }}
table {{ border-collapse: collapse; width: 100%; margin: 2mm 0 4mm; font-size: 9.6pt; break-inside: auto; }}
th {{ background: var(--navy); color: white; font-weight: 600; text-align: left; padding: 1.8mm 2.4mm; }}
td {{ border-bottom: 1px solid var(--border); padding: 1.6mm 2.4mm; vertical-align: top; }}
tr:nth-child(even) td {{ background: #FAFBFD; }}
td.num {{ width: 9mm; }}
.dot, .mark {{ display: inline-flex; align-items: center; justify-content: center; width: 6mm; height: 6mm;
   border-radius: 50%; background: #F2A40E; color: #1E2433; font-weight: 700; font-size: 8.5pt;
   border: 1.5px solid white; box-shadow: 0 0 0 1px rgba(0,0,0,.25); }}
.annot-wrap {{ position: relative; }}
.mark {{ position: absolute; transform: translate(-50%, -50%); }}
.note, .warn, .tip {{ border-radius: 6px; padding: 2.6mm 3.6mm; margin: 3mm 0; break-inside: avoid; }}
.note {{ background: var(--info); border-left: 4px solid #2F6FD6; }}
.warn {{ background: var(--warn); border-left: 4px solid #E3A10E; }}
.tip {{ background: var(--soft); border-left: 4px solid var(--purple); }}
.steps {{ counter-reset: s; list-style: none; padding: 0; margin: 2mm 0 4mm; }}
.steps li {{ counter-increment: s; position: relative; padding: 1.2mm 0 1.2mm 11mm; }}
.steps li::before {{ content: counter(s); position: absolute; left: 0; top: 1.2mm; width: 7mm; height: 7mm;
   border-radius: 50%; background: var(--purple); color: white; font-weight: 600; display: flex;
   align-items: center; justify-content: center; font-size: 9pt; }}
kbd {{ font-family: Plex; background: #F3F4F8; border: 1px solid var(--border); border-bottom-width: 2px;
   border-radius: 4px; padding: 0 1.6mm; font-size: 9pt; }}
code {{ font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 8.8pt; background: #F3F4F8;
   padding: 0 1mm; border-radius: 3px; }}
.cover {{ height: 297mm; width: 210mm; position: relative; background: var(--bg); overflow: hidden; }}
.cover .band {{ background: var(--navy); color: white; padding: 26mm 18mm 14mm; }}
.cover .logo {{ width: 16mm; height: 16mm; border-radius: 4mm; background: var(--purple); display: inline-flex;
   align-items: center; justify-content: center; margin-bottom: 7mm; }}
.cover h0 {{ display: block; font-size: 30pt; font-weight: 700; letter-spacing: .2px; }}
.cover .sub {{ font-size: 15pt; color: #C9D2EA; margin-top: 2mm; }}
.cover .kicker {{ font-size: 10pt; color: #AFC0EA; margin-top: 7mm; }}
.cover .shot {{ margin: 12mm 14mm 0; }}
.cover .shot img {{ width: 100%; border-radius: 6px; box-shadow: 0 6px 24px rgba(31,43,77,.25); }}
.cover .meta {{ position: absolute; bottom: 16mm; left: 18mm; right: 18mm; font-size: 9.5pt; color: var(--muted);
   display: flex; justify-content: space-between; border-top: 1px solid var(--border); padding-top: 3mm; }}
.toc {{ columns: 2; column-gap: 10mm; font-size: 10.5pt; }}
.toc div {{ padding: 1mm 0; border-bottom: 1px dotted var(--border); break-inside: avoid; }}
.toc .n {{ color: var(--purple); font-weight: 600; display: inline-block; width: 8mm; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }}
.missing {{ border: 1px dashed #C93636; color: #C93636; padding: 4mm; text-align: center; }}
"""
    sec = []
    sec.append(f"""
<div class="cover">
 <div class="band">
  <div class="logo"><svg width="36" height="36" viewBox="0 0 24 24"><path d="M2 12 Q12 1 22 12 Q12 23 2 12Z"
   fill="none" stroke="white" stroke-width="1.8"/><circle cx="12" cy="12" r="3.5" fill="white"/></svg></div>
  <h0>Vision Model Inspector</h0>
  <div class="sub">คู่มือการใช้งาน • UI แบบ C วิเคราะห์เปรียบเทียบ</div>
  <div class="kicker">เปิดโมเดลตรวจจับวัตถุที่คุณฝึกเอง • วิเคราะห์ภาพ วิดีโอ และกล้อง • Grad-CAM รายวัตถุ</div>
 </div>
 <div class="shot"><img src="{uri(os.path.join(shots, '01_main.png'))}"/></div>
 <div class="meta"><span>เวอร์ชัน {__version__} (แพ็กเกจ CPU) • Windows 10/11 x64</span>
  <span>ฉบับวันที่ {facts.get('date_th', '')}</span></div>
</div>""")

    toc = ["ภาพรวมโปรแกรม", "ความต้องการของระบบ", "การติดตั้งและถอนการติดตั้ง", "ส่วนประกอบของหน้าจอ",
           "เริ่มใช้งานอย่างรวดเร็ว", "การเปิดโมเดล", "คลาสและหน้าจัดการคลาส", "แหล่งภาพและกล้อง",
           "การตรวจจับแบบสด", "การจับภาพและแถบภาพที่บันทึก", "การวิเคราะห์ Grad-CAM", "การส่งออกผล",
           "คีย์ลัด", "การแก้ปัญหา", "ข้อจำกัดและหมายเหตุสำคัญ", "สัญญาอนุญาตและแหล่งที่มา"]
    sec.append("<section style='break-before:page'><h1>สารบัญ</h1><div class='toc'>" +
               "".join(f"<div><span class='n'>{i}</span>{t}</div>" for i, t in enumerate(toc, 1)) +
               "</div>" + """
<div class="note" style="margin-top:8mm"><b>เกี่ยวกับภาพในคู่มือ</b> — ภาพหน้าจอทั้งหมดถ่ายจากโปรแกรมจริงที่รันบน
Windows (CI runner) ด้วยโมเดลตัวอย่างทางการของ Ultralytics (yolov8n.pt, yolo11n.pt) บน CPU ไม่ใช่ภาพจำลอง
ชื่อคลาสภาษาไทยในภาพ (เช่น "คน", "รถบัส") คือ <i>ชื่อแสดงผล</i> ที่ตั้งในหน้าจัดการคลาส ไม่ได้มาจากการแปลอัตโนมัติ</div>
</section>""")

    sec.append("""
<section><h1><span class="n">1</span>ภาพรวมโปรแกรม</h1>
<p>Vision Model Inspector เป็นโปรแกรมบน Windows สำหรับเปิด <b>โมเดลตรวจจับวัตถุ (Object Detection)</b> ที่คุณฝึกไว้
แล้วนำไปวิเคราะห์ภาพนิ่ง โฟลเดอร์ภาพ วิดีโอ หรือกล้องแบบสด จากนั้น <b>จับภาพ (snapshot)</b> ที่สนใจมาตรวจดูผลอย่างละเอียด
และดูว่าโมเดล "มอง" บริเวณใดของภาพเมื่อตัดสินใจเรื่องวัตถุแต่ละชิ้นด้วย <b>Grad-CAM</b></p>
<p>โปรแกรมเป็นเครื่องมือทั่วไป ไม่ผูกกับงานหรือชุดข้อมูลใด ชื่อคลาสและจำนวนคลาสอ่านจากโมเดลที่เปิดทุกครั้ง</p>
<h2>สิ่งที่โปรแกรมทำได้</h2>
<table><tr><th style="width:32%">ความสามารถ</th><th>รายละเอียด</th></tr>
<tr><td>โมเดลที่รองรับ</td><td>Ultralytics <b>YOLOv8</b> และ <b>YOLO11</b> (task detect) แบบ <code>.pt</code> และไฟล์ <code>.onnx</code>
ที่ export จาก Ultralytics (ทดสอบกับ Ultralytics 8.3)</td></tr>
<tr><td>แหล่งภาพ</td><td>JPG/JPEG/PNG, โฟลเดอร์ภาพ, วิดีโอ, กล้อง USB/ในเครื่อง, IP Camera (RTSP), ระบุ index/backend เอง</td></tr>
<tr><td>Grad-CAM</td><td>ต่อ <b>วัตถุแต่ละชิ้น</b> (detection instance) บน snapshot ที่เลือก เฉพาะโมเดล <code>.pt</code> ที่รองรับ</td></tr>
<tr><td>การส่งออก</td><td>ภาพต้นฉบับ ภาพกรอบ Heatmap ภาพซ้อน ภาพเปรียบเทียบ CSV และ JSON metadata</td></tr>
<tr><td>อุปกรณ์</td><td>CPU (ไม่ต้องมี GPU) — แพ็กเกจนี้เป็นรุ่น CPU</td></tr></table>
<h2>สิ่งที่โปรแกรมไม่ทำ</h2>
<ul><li>ไม่ฝึก (train) โมเดล และตัวกรองคลาสไม่ได้เปลี่ยนความสามารถของโมเดล</li>
<li>ไม่แสดง accuracy / mAP / precision / recall เพราะไม่มีชุดข้อมูลเฉลย (ground truth) — <b>ค่าความมั่นใจคือ score ของโมเดล ไม่ใช่ความแม่นยำ</b></li>
<li>จำนวนวัตถุที่แสดงเป็น <b>จำนวนต่อเฟรม</b> ไม่ใช่จำนวนสะสมที่ไม่ซ้ำ (ไม่มี tracking)</li>
<li>ไม่ส่งภาพหรือโมเดลออกไปภายนอก และไม่บันทึกทุกเฟรมโดยอัตโนมัติ</li></ul>
</section>""")

    sec.append(f"""
<section><h1><span class="n">2</span>ความต้องการของระบบ</h1>
<table><tr><th style="width:26%">รายการ</th><th style="width:37%">ขั้นต่ำ</th><th>แนะนำ</th></tr>
<tr><td>ระบบปฏิบัติการ</td><td>Windows 10 x64 (1809 ขึ้นไป)</td><td>Windows 11 x64</td></tr>
<tr><td>CPU</td><td>x64 4 threads รองรับ AVX2</td><td>8 threads ขึ้นไป</td></tr>
<tr><td>หน่วยความจำ</td><td>8 GB</td><td>16 GB</td></tr>
<tr><td>พื้นที่ดิสก์</td><td>{facts.get('disk_req', '2 GB')}</td><td>เผื่อพื้นที่สำหรับไฟล์ส่งออก</td></tr>
<tr><td>หน้าจอ</td><td>1366 × 768</td><td>1920 × 1080 ขึ้นไป (รองรับ DPI scaling)</td></tr>
<tr><td>GPU</td><td>ไม่ต้องมี</td><td>แพ็กเกจนี้ไม่ใช้ GPU (ดูหัวข้อ 15)</td></tr></table>
<div class="note"><b>ผลทดสอบจริงบน CPU</b> (Windows Server 2022, AMD EPYC 4 vCPU, RAM 16 GB, ขนาด input 640):
{perf.get('summary', 'ดูรายงานการทดสอบ')}<br/>ความเร็วจริงขึ้นกับ CPU ขนาดภาพ ขนาด input และขนาดโมเดล — ไม่รับประกันว่าทุกเครื่องได้ FPS เท่ากัน</div>
<p>Windows ARM และ Windows 32-bit อยู่นอกขอบเขตของรุ่นนี้</p>
</section>""")

    sec.append("""
<section><h1><span class="n">3</span>การติดตั้งและถอนการติดตั้ง</h1>
<h2>ติดตั้ง</h2>
<ol class="steps">
<li>ดับเบิลคลิกไฟล์ <code>VisionModelInspector-0.1.0-cpu-setup.exe</code></li>
<li>ถ้า Windows SmartScreen แจ้งว่าไฟล์ไม่รู้จัก (ตัวติดตั้งยังไม่ได้ลงนามดิจิทัล) ให้ตรวจว่าได้ไฟล์จากแหล่งของคุณเองแล้วเลือก
<i>More info › Run anyway</i> — ไม่ต้องปิดโปรแกรมป้องกันไวรัสหรือระบบความปลอดภัยใด ๆ</li>
<li>เลือกติดตั้งสำหรับ <b>ผู้ใช้ปัจจุบัน</b> (ไม่ต้องใช้สิทธิ์ผู้ดูแล) หรือสำหรับทุกผู้ใช้</li>
<li>ยอมรับสัญญาอนุญาต (AGPL-3.0) เลือกตำแหน่งติดตั้ง และเลือกสร้าง shortcut บนเดสก์ท็อปได้</li>
<li>กด Install แล้วเปิดโปรแกรมจากเมนู Start › Vision Model Inspector</li></ol>
<div class="tip">ไม่ต้องติดตั้ง Python และไม่ต้องเปิด Terminal — ตัวติดตั้งรวม Python runtime, PyTorch (CPU), ONNX Runtime,
OpenCV, Qt และฟอนต์ภาษาไทยไว้แล้ว ใช้งานแบบ offline ได้กับไฟล์และกล้อง USB หลังติดตั้งเสร็จ</div>
<h2>ไฟล์ของผู้ใช้</h2>
<table><tr><th style="width:40%">ตำแหน่ง</th><th>เนื้อหา</th></tr>
<tr><td><code>%LOCALAPPDATA%\\VisionModelInspector\\settings.json</code></td><td>ค่าตั้ง โมเดลล่าสุด กล้องที่เลือก</td></tr>
<tr><td><code>…\\display_names.json</code></td><td>ชื่อแสดงผลและตัวกรองคลาส (แยกตาม SHA-256 ของโมเดล)</td></tr>
<tr><td><code>…\\logs\\vmi.log</code></td><td>บันทึกการทำงาน (ไม่มีรหัสผ่าน)</td></tr></table>
<h2>ถอนการติดตั้ง</h2>
<p>Settings › Apps › Installed apps › Vision Model Inspector › Uninstall หรือเมนู Start › Uninstall Vision Model Inspector
(ไฟล์ค่าตั้งใน %LOCALAPPDATA% ไม่ถูกลบ ลบเองได้หากไม่ต้องการ)</p>
</section>""")

    sec.append(f"""
<section><h1><span class="n">4</span>ส่วนประกอบของหน้าจอ</h1>
{annotated_main(shots, geo)}
<table><tr><th class="num">#</th><th style="width:30%">ส่วน</th><th>หน้าที่</th></tr>{callout_rows}</table>
<div class="tip">หน้าจอปรับขนาดได้ ลากเส้นแบ่งระหว่างแผงเพื่อขยายภาพ และใช้ได้ตั้งแต่ความละเอียด 1366 × 768 (แผงตั้งค่าเลื่อนขึ้นลงได้)</div>
{figure(shots, '07_main_1366x768.png', 'รูปที่ 2 หน้าจอเดียวกันที่ขนาด 1366 × 768', 'half')}
</section>""")

    sec.append("""
<section><h1><span class="n">5</span>เริ่มใช้งานอย่างรวดเร็ว</h1>
<ol class="steps">
<li>กด <b>เปิดโมเดล…</b> เลือกไฟล์ <code>.pt</code> หรือ <code>.onnx</code> (ไฟล์ .pt จะมีหน้าต่างยืนยันความปลอดภัยก่อนโหลด)</li>
<li>เลือก <b>แหล่งข้อมูล</b>: กล้อง วิดีโอ รูปภาพ หรือโฟลเดอร์ภาพ แล้วเลือกกล้อง/ไฟล์</li>
<li>กด <b>เริ่ม</b> — ภาพสดมุมซ้ายบนจะแสดงกรอบตรวจจับของเฟรมนั้น ๆ</li>
<li>เมื่อเห็นภาพที่ต้องการ กด <b>จับภาพ</b> (หรือ <kbd>Space</kbd>) ภาพจะไปอยู่ในแถบ "ภาพที่บันทึก" และแสดงในแผงซ้าย</li>
<li>เลือกวัตถุจากตารางหรือคลิกกรอบบนภาพ แล้วกด <b>วิเคราะห์</b> เพื่อดู Grad-CAM ในแผงขวา</li>
<li>กด <b>ส่งออก…</b> เพื่อบันทึกภาพ CSV และ metadata ไปยังโฟลเดอร์ที่เลือก</li></ol>
<div class="note">ปุ่มต่าง ๆ จะกดได้ตามสถานะจริง เช่น "จับภาพ" ต้องเปิดโมเดลและมีภาพจากแหล่งภาพก่อน,
"วิเคราะห์" ต้องเลือกวัตถุบน snapshot ที่ตรวจด้วยโมเดลปัจจุบันและโมเดลรองรับ Grad-CAM — วางเมาส์บนปุ่มเพื่อดูเหตุผล</div>
</section>""")

    sec.append(f"""
<section><h1><span class="n">6</span>การเปิดโมเดล</h1>
<h2>ไฟล์ .pt (PyTorch / Ultralytics)</h2>
<p>รองรับ checkpoint ของ Ultralytics YOLOv8 และ YOLO11 ที่เป็น task <b>detect</b> เท่านั้น
ไฟล์ .pt ประเภทอื่น (เช่น classification, segmentation หรือไฟล์ PyTorch ทั่วไป) จะถูกปฏิเสธพร้อมเหตุผล</p>
<div class="warn"><b>ความปลอดภัย:</b> ไฟล์ .pt โหลดด้วย pickle ซึ่งรันโค้ดได้ขณะเปิดไฟล์ โปรแกรมจึงถามยืนยันก่อนโหลด
และแสดง SHA-256 ของไฟล์ — เปิดเฉพาะไฟล์ที่คุณฝึกเองหรือได้จากแหล่งที่เชื่อถือได้ ติ๊ก "เชื่อถือไฟล์นี้" เพื่อไม่ต้องถามซ้ำ
โปรแกรมไม่ติดตั้งแพ็กเกจหรือรันสคริปต์อื่นที่มากับโมเดล</div>
<h2>ไฟล์ .onnx</h2>
<p>รองรับไฟล์ที่ export จาก Ultralytics (YOLOv8/YOLO11 detect) ที่มี output รูปแบบที่รู้จัก: <code>(1, 4+nc, A)</code>,
<code>(1, A, 4+nc)</code> หรือแบบรวม NMS <code>(1, N, 6)</code> — หากไม่รู้จักรูปแบบ output โปรแกรมจะแจ้งและไม่เดา
<b>Grad-CAM ปิดสำหรับ ONNX</b> ในรุ่นนี้ ให้ใช้ไฟล์ .pt ของโมเดลเดียวกันแทน
ถ้า ONNX มี input ขนาดคงที่ ช่อง "ขนาด input" จะล็อกตามโมเดล</p>
<h2>ข้อมูลโมเดล</h2>
<p>กด <b>ข้อมูลโมเดล…</b> ในแผงตั้งค่าเพื่อดูชื่อและชนิดไฟล์ SHA-256 adapter task input shape รูปแบบ output
จำนวนคลาสและแหล่งที่มา device สถานะ inference สถานะ Grad-CAM และข้อจำกัดสำคัญ</p>
{figure(shots, '04_model_info.png', 'รูปที่ 3 หน้าต่างข้อมูลโมเดล', 'small')}
<h2>เปลี่ยนโมเดล</h2>
<p>เปิดโมเดลใหม่ได้ตลอดเวลา โปรแกรมจะรอให้งานตรวจจับที่กำลังทำเสร็จ คืนหน่วยความจำของโมเดลเดิม แล้วโหลดคลาสและค่าตั้งใหม่
ภาพที่บันทึกไว้ก่อนหน้า <b>ยังเก็บชื่อโมเดล SHA-256 และชื่อคลาสของโมเดลเดิม</b> ไม่ถูกเปลี่ยนป้ายย้อนหลัง</p>
</section>""")

    sec.append(f"""
<section><h1><span class="n">7</span>คลาสและหน้าจัดการคลาส</h1>
<p>ชื่อคลาสอ่านตามลำดับความสำคัญ: (1) metadata ในโมเดล เช่น <code>model.names</code> (2) metadata ในไฟล์ ONNX
(3) ไฟล์ที่ผู้ใช้นำเข้า (4) หากไม่มีชื่อเลย ใช้ <code>class_0, class_1, …</code> ตามรหัสที่ตรวจได้ และแจ้งว่ายังไม่มีชื่อ
โปรแกรมไม่เดาชื่อจากภาพหรือชื่อไฟล์ และไม่แปลชื่อคลาสอัตโนมัติ</p>
{figure(shots, '03_class_manager.png', 'รูปที่ 4 หน้าจัดการคลาส', 'half')}
<h2>สิ่งที่ทำได้ในหน้าจัดการคลาส</h2>
<ul><li><b>ชื่อแสดงผล</b> — ตั้งชื่อภาษาไทยเองต่อ class_id ชื่อต้นฉบับยังคงอยู่ เก็บแยกจากไฟล์โมเดล (อ้างอิง SHA-256 + class_id)</li>
<li><b>ตัวกรองการแสดงผล</b> — "แสดงทุกคลาส" หรือ "แสดงเฉพาะคลาสที่เลือก" มีผลกับภาพ ตาราง และ (ถ้าเลือก) ไฟล์ส่งออก
<i>ไม่ได้เปลี่ยนความสามารถของโมเดล</i></li>
<li><b>ค้นหาคลาส</b> ตามรหัส ชื่อต้นฉบับ หรือชื่อแสดงผล</li>
<li><b>นำเข้า mapping</b> จาก <code>data.yaml</code>, <code>classes.txt</code> หรือ JSON</li></ul>
<h2>รูปแบบไฟล์ mapping</h2>
<table><tr><th style="width:22%">ไฟล์</th><th>รูปแบบ</th></tr>
<tr><td>data.yaml</td><td><code>names: [ok, รอยร้าว, สนิม]</code> หรือ <code>names: {{0: ok, 1: รอยร้าว}}</code> (มี <code>nc</code> ได้ ต้องตรงกับจำนวนชื่อ)</td></tr>
<tr><td>classes.txt</td><td>1 บรรทัด = 1 คลาส <b>บรรทัดแรกคือรหัส 0</b> ห้ามมีบรรทัดว่างคั่น (UTF-8)</td></tr>
<tr><td>JSON</td><td><code>["ok", "รอยร้าว"]</code> หรือ <code>{{"0": "ok", "1": "รอยร้าว"}}</code></td></tr></table>
<div class="warn">ชื่อที่นำเข้า <b>ต้องเรียงตรงกับลำดับตอนฝึกโมเดล</b> ถ้าจำนวนคลาสไม่ตรงกับ output ของโมเดล ไฟล์เสีย หรือรหัสไม่ต่อเนื่อง
โปรแกรมจะแจ้งข้อผิดพลาด ถ้าชื่อในไฟล์ขัดกับชื่อในโมเดล จะแสดงรายการที่ต่างกันและให้คุณยืนยันเอง ไม่มีการแก้ไขเงียบ ๆ</div>
</section>""")

    sec.append(f"""
<section><h1><span class="n">8</span>แหล่งภาพและกล้อง</h1>
<h2>รูปภาพ / โฟลเดอร์ภาพ / วิดีโอ</h2>
<p>เลือกแหล่งข้อมูลในแถบด้านบน กด <b>เลือก…</b> แล้วกด <b>เริ่ม</b> โฟลเดอร์ภาพใช้ปุ่ม ◀ ▶ ที่แผงภาพสดเพื่อเปลี่ยนภาพ
วิดีโอหยุดชั่วคราวได้ด้วยปุ่มหยุดชั่วคราว (สัญลักษณ์ II) รองรับชื่อไฟล์และโฟลเดอร์ภาษาไทย</p>
<h2>กล้อง USB / ในเครื่อง</h2>
<p>โปรแกรมค้นหากล้องตามที่ Windows มองเห็น (Qt Multimedia) และเปิดกล้องด้วย <b>รหัสอุปกรณ์จริง</b>
ไม่ใช่การเดาลำดับ index — กล้องชื่อซ้ำจะแสดงรหัสย่อช่วยแยก กด ⟳ เพื่อรีเฟรช และกด ⚙ เพื่อเปิดหน้าต่างเลือกกล้อง
ที่แสดงชื่อ ประเภท backend สถานะ ความละเอียด/FPS ที่อุปกรณ์รายงาน และปุ่ม <b>ทดสอบภาพ</b></p>
{figure(shots, '05_camera_dialog.png', 'รูปที่ 5 หน้าต่างเลือกกล้อง (เครื่องที่ถ่ายภาพนี้ไม่มีกล้องต่ออยู่)', 'half')}
<p>กล้องที่เลือกจะถูกจำไว้ ถ้าครั้งต่อไปไม่พบกล้องนั้น โปรแกรมจะแจ้งและให้เลือกใหม่ — <b>ไม่สลับไปกล้องอื่นเอง</b>
ถ้ากล้องถูกถอดระหว่างใช้งาน โปรแกรมจะหยุดรับภาพและแจ้งเตือน</p>
<div class="two"><div>{figure(shots, '05c_camera_manual.png', 'รูปที่ 6 แท็บ "ระบุเอง (ขั้นสูง)"')}</div>
<div>{figure(shots, '05b_camera_rtsp.png', 'รูปที่ 7 แท็บ IP Camera (RTSP)')}</div></div>
<h2>ระบุเอง (ขั้นสูง)</h2>
<p>ใช้เมื่อกล้องไม่ปรากฏในรายการ: ระบุ index และ backend ของ OpenCV (DirectShow / Media Foundation) ขนาดภาพที่ขอ
และ timeout แล้วกดทดสอบ ค่าที่ใช้งานได้จริงแสดงหลังเชื่อมต่อ ไม่รับประกันว่าทุกอุปกรณ์ใน Device Manager จะเปิดได้</p>
<h2>IP Camera (RTSP)</h2>
<p>เพิ่ม URL เอง ตั้งชื่อ กำหนด timeout และจำนวนครั้งที่เชื่อมต่อใหม่ กด "หยุด / ยกเลิก" เพื่อยกเลิกการเชื่อมต่อ
รหัสผ่านไม่ถูกเขียนลง log; ถ้าเลือก "จำรหัสผ่าน" จะเข้ารหัสด้วย Windows DPAPI (ผูกกับบัญชีผู้ใช้) โปรแกรมไม่สแกนเครือข่ายอัตโนมัติ</p>
<h2>กล้องอุตสาหกรรม</h2>
<p>กล้อง GigE Vision / USB3 Vision มักต้องใช้ SDK และ adapter เฉพาะของผู้ผลิต — รุ่นนี้ยังไม่รองรับโดยตรง
(ถ้าผู้ผลิตมีไดรเวอร์ DirectShow/Media Foundation อาจใช้ผ่านแท็บ "ระบุเอง" ได้)</p>
</section>""")

    sec.append("""
<section><h1><span class="n">9</span>การตรวจจับแบบสด</h1>
<table><tr><th style="width:30%">ค่าตั้ง</th><th>ความหมาย</th></tr>
<tr><td>เกณฑ์ความมั่นใจ</td><td>แสดงเฉพาะวัตถุที่ score ≥ ค่านี้ (ค่าเริ่มต้น 0.25)</td></tr>
<tr><td>เกณฑ์ IoU (NMS)</td><td>กรอบที่ซ้อนกันเกินค่านี้ในคลาสเดียวกันจะเหลือกรอบเดียว (ไม่มีผลกับ ONNX ที่รวม NMS แล้ว)</td></tr>
<tr><td>ขนาด input</td><td>ขนาดภาพที่ป้อนโมเดล (ภาพถูกย่อแบบรักษาสัดส่วนและเติมขอบ) ใหญ่ขึ้นเห็นวัตถุเล็กดีขึ้นแต่ช้าลง</td></tr>
<tr><td>อัตราการตรวจจับสด</td><td>"ทุก N เฟรม" และ "สูงสุด X FPS" เพื่อลดภาระ CPU</td></tr>
<tr><td>อุปกรณ์ประมวลผล</td><td>อัตโนมัติ / CPU / CUDA (CUDA ใช้ไม่ได้ในแพ็กเกจ CPU — เมนูจะปิดพร้อมเหตุผล)</td></tr></table>
<h2>ตัวเลขในแถบสถานะ</h2>
<ul><li><b>Capture FPS</b> — จำนวนเฟรมที่ได้รับจากแหล่งภาพต่อวินาที</li>
<li><b>Inference FPS • ms/ภาพ</b> — จำนวนเฟรมที่ตรวจจับต่อวินาที และเวลาประมวลผลต่อภาพ (เตรียมภาพ + โมเดล + NMS ไม่รวมการแสดงผล)</li>
<li><b>วัตถุในเฟรม</b> — จำนวนต่อเฟรมล่าสุด ไม่ใช่จำนวนสะสม</li></ul>
<div class="note">ภาพสดแสดงกรอบบน <b>เฟรมเดียวกับที่ใช้คำนวณ</b> เสมอ เมื่อ CPU ช้ากว่ากล้อง ภาพสดที่มีกรอบจะอัปเดตตามความเร็ว inference
และเฟรมที่ประมวลผลไม่ทันจะถูกข้าม (ไม่ต่อคิว) จึงไม่ใช้หน่วยความจำเพิ่มเรื่อย ๆ</div>
</section>""")

    sec.append(f"""
<section><h1><span class="n">10</span>การจับภาพและแถบภาพที่บันทึก</h1>
<p>กด <b>จับภาพ</b> เพื่อเก็บสำเนาภาพพร้อมผลตรวจจับของภาพนั้น ชื่อโมเดล SHA-256 ชื่อคลาส และค่าตั้งขณะนั้น
แต่ละภาพมีหมายเลข (ภาพที่ 01, 02, …) และเวลา แสดงตรงกันทั้งแผงผลตรวจและแผง Grad-CAM</p>
<ul><li>คลิกภาพในแถบเพื่อเลือก ดับเบิลคลิกเพื่อเปิดดูขนาดใหญ่ คลิกขวาเพื่อ เปิดดู / ส่งออก / ลบ / ล้างทั้งหมด</li>
<li>กำหนด <b>ขีดจำกัดหน่วยความจำ</b> (จำนวนภาพและ MB) ในแผงตั้งค่า เมื่อเกิน ภาพเก่าสุดจะถูกลบออกจากรายการอัตโนมัติ</li>
<li>ในแผงผลตรวจ: ล้อเมาส์ = ซูม, ลาก = เลื่อน, ดับเบิลคลิก = พอดีกรอบ, ติ๊ก <b>ซิงก์มุมมอง</b> เพื่อซูม/เลื่อนสองฝั่งพร้อมกัน</li></ul>
{figure(shots, '08_onnx_model.png', 'รูปที่ 8 ผลตรวจจากโมเดล ONNX (yolov8n.onnx) — แผง Grad-CAM แจ้งว่าไม่รองรับสำหรับ ONNX', 'half')}
</section>""")

    sec.append(f"""
<section><h1><span class="n">11</span>การวิเคราะห์ Grad-CAM</h1>
<div class="warn"><b>Grad-CAM วิเคราะห์ภาพที่เลือก ไม่ใช่ภาพสด และแผนที่สีไม่ใช่ค่าความแม่นยำ</b></div>
<ol class="steps"><li>เลือก snapshot จากแถบภาพที่บันทึก</li>
<li>เลือก <b>วัตถุเป้าหมาย</b> (วัตถุชิ้นเดียว แม้มีหลายชิ้นในคลาสเดียวกัน) จากตาราง คลิกกรอบ หรือช่อง "วัตถุเป้าหมาย"</li>
<li>เลือก <b>ชั้นเป้าหมาย</b>: "อัตโนมัติ (แนะนำ)" ใช้ feature map ของ head ระดับ P3/P4/P5 ที่ตรงกับวัตถุ หรือเลือกชั้นเอง</li>
<li>กด <b>วิเคราะห์</b> — ระหว่างคำนวณ การตรวจจับสดจะพักชั่วคราว (ภาพสดยังแสดง) และมีป้าย "พักตรวจจับ"</li>
<li>เลือก <b>วิธีคำนวณ</b>: Grad-CAM (มาตรฐาน) หรือ HiResCAM (ละเอียดรายวัตถุ) — ดูหัวข้อถัดไป</li>
<li>ปรับ <b>ความทึบแผนที่สี</b> ได้ทันทีโดยไม่ต้องคำนวณใหม่</li></ol>
{figure(shots, '02_gradcam_running.png', 'รูปที่ 9 ระหว่างคำนวณ Grad-CAM แผงขวาแสดงสถานะจริง (ไม่มี Heatmap จำลอง)', 'half')}
<h2>Grad-CAM กับ HiResCAM ต่างกันอย่างไร</h2>
<p><b>Grad-CAM</b> (Selvaraju et al., 2017) เฉลี่ย gradient ของแต่ละ channel ทั่วทั้งแผนที่ก่อนถ่วงน้ำหนัก
จึงมักไฮไลต์ <i>ทุกบริเวณที่คล้ายคลาสนั้น</i> เช่น คนทุกคนในภาพ แม้คุณเลือกเพียงคนเดียว
<b>HiResCAM</b> (Draelos &amp; Carin, 2020) คูณ gradient กับ activation ทีละตำแหน่งโดยไม่เฉลี่ย จึงสะท้อน
<i>วัตถุชิ้นที่เลือก</i> ได้ตรงกว่า — เหมาะเมื่อในภาพมีวัตถุคลาสเดียวกันหลายชิ้น ทั้งสองวิธีใช้ target และชั้นเดียวกัน</p>
<div class="two"><div>{figure(shots, '01_main.png', 'รูปที่ 10 Grad-CAM มาตรฐาน: เน้นหลายบริเวณในภาพ')}</div>
<div>{figure(shots, '09_hirescam.png', 'รูปที่ 11 HiResCAM ของวัตถุเดียวกัน: เน้นที่คนที่เลือก')}</div></div>
<h2>อ่านผลอย่างไร</h2>
<p>สีแดง/เหลืองคือบริเวณที่ gradient ของ score ของวัตถุนั้นต่อ feature map มีผลเชิงบวกมาก — บอกว่าโมเดล "อาศัย" ส่วนใดของภาพ
ไม่ได้บอกว่าโมเดลถูกหรือผิด ใต้ภาพจะแสดงชั้นที่ใช้ anchor ก่อน NMS ที่จับคู่ได้ ค่า IoU ของการจับคู่ score และเวลา
(ตัวอย่างจากภาพในคู่มือ: IoU {gc.get('match_iou', 0):.3f}, score ต่างจากผลตรวจ {gc.get('score_difference', 0):.4f}, {gc.get('matched_level', '')})</p>
<p>หากจับคู่วัตถุกับผลก่อน NMS ไม่ได้, gradient เป็นศูนย์ หรือชั้นนั้นใช้ไม่ได้ โปรแกรมจะแจ้งเหตุผลเป็นสีแดงและ <b>ไม่สร้าง Heatmap แทน</b></p>
<div class="note">Grad-CAM ต้องใช้โมเดลเดียวกับที่ตรวจ snapshot นั้น ถ้าเปลี่ยนโมเดลแล้ว ปุ่มวิเคราะห์จะปิดสำหรับภาพเก่า
และใช้ได้เฉพาะไฟล์ .pt (YOLOv8/YOLO11)</div>
</section>""")

    sec.append(f"""
<section><h1><span class="n">12</span>การส่งออกผล</h1>
{figure(shots, '06_export_dialog.png', 'รูปที่ 12 หน้าต่างส่งออก', 'small')}
<p>ทุกครั้งที่ส่งออก โปรแกรมสร้างโฟลเดอร์ย่อยใหม่ เช่น <code>ภาพ03_20261015-102425_yolov8n</code> — ไม่เขียนทับไฟล์เดิม
ถ้าชื่อซ้ำจะเติม (2), (3) อัตโนมัติ รองรับชื่อโฟลเดอร์ภาษาไทยและช่องว่าง</p>
<table><tr><th style="width:30%">ไฟล์</th><th>เนื้อหา</th></tr>
<tr><td>original.png</td><td>สำเนาภาพต้นฉบับ (ไม่บีบอัดแบบสูญเสีย)</td></tr>
<tr><td>detections.png</td><td>ภาพพร้อมกรอบและชื่อคลาส</td></tr>
<tr><td>gradcam_heatmap.png / gradcam_overlay.png</td><td>แผนที่สี และภาพซ้อนตามความทึบที่ตั้ง</td></tr>
<tr><td>comparison.png</td><td>ภาพผลตรวจและ Grad-CAM เคียงกัน</td></tr>
<tr><td>detections.csv</td><td>หนึ่งแถวต่อวัตถุ: รหัส/ชื่อคลาส ความมั่นใจ กรอบ (UTF-8 เปิดใน Excel เห็นภาษาไทย)</td></tr>
<tr><td>metadata.json</td><td>SHA-256 โมเดล class mapping frame ID เวลา device เวอร์ชันไลบรารี การเตรียมภาพ และค่าตั้ง/ชั้น/target ของ Grad-CAM</td></tr></table>
<p>ไฟล์บันทึกในเครื่องนี้เท่านั้น โปรแกรมไม่ส่งภาพหรือโมเดลออกไปภายนอก</p>
</section>""")

    sec.append("""
<section><h1><span class="n">13</span>คีย์ลัด</h1>
<table><tr><th style="width:28%">คีย์</th><th>การทำงาน</th></tr>
<tr><td><kbd>Ctrl</kbd> + <kbd>O</kbd></td><td>เปิดโมเดล</td></tr>
<tr><td><kbd>Space</kbd></td><td>จับภาพ</td></tr>
<tr><td><kbd>Ctrl</kbd> + <kbd>G</kbd></td><td>วิเคราะห์ Grad-CAM</td></tr>
<tr><td><kbd>Ctrl</kbd> + <kbd>E</kbd></td><td>ส่งออก</td></tr>
<tr><td><kbd>F5</kbd></td><td>รีเฟรชรายการกล้อง</td></tr>
<tr><td><kbd>Delete</kbd></td><td>ลบภาพที่เลือกออกจากรายการ</td></tr>
<tr><td>ล้อเมาส์ / ลาก / ดับเบิลคลิก</td><td>ซูม / เลื่อน / พอดีกรอบ ในแผงภาพ</td></tr></table>
<h1 style="margin-top:10mm"><span class="n">14</span>การแก้ปัญหา</h1>
<table><tr><th style="width:34%">อาการ</th><th>สาเหตุและวิธีแก้</th></tr>
<tr><td>ไม่พบกล้องในรายการ</td><td>ตรวจสาย USB กด ⟳, เปิดสิทธิ์ที่ Settings › Privacy &amp; security › Camera ("Let desktop apps access your camera")
หรือใช้แท็บ "ระบุเอง"</td></tr>
<tr><td>เปิดกล้องไม่สำเร็จ / timeout</td><td>กล้องอาจถูกใช้งานโดยโปรแกรมอื่น (Teams, Zoom, Camera) ให้ปิดโปรแกรมนั้นแล้วเริ่มใหม่</td></tr>
<tr><td>"เลือก CUDA แต่ใช้งานไม่ได้"</td><td>แพ็กเกจนี้เป็นรุ่น CPU — เลือก CPU หรืออัตโนมัติ</td></tr>
<tr><td>เปิดไฟล์ .pt ไม่ได้</td><td>ไฟล์ต้องเป็น Ultralytics YOLOv8/YOLO11 detect; segmentation/classification/pose และ checkpoint อื่นไม่รองรับในรุ่นนี้</td></tr>
<tr><td>ONNX "ไม่รู้จักรูปแบบ output"</td><td>export ใหม่จาก Ultralytics (<code>format=onnx</code>) หรือใช้ไฟล์ .pt</td></tr>
<tr><td>ชื่อคลาสเป็น class_0, class_1</td><td>โมเดลไม่มี metadata ชื่อคลาส — นำเข้า data.yaml / classes.txt ในหน้าจัดการคลาส</td></tr>
<tr><td>ตรวจจับช้า</td><td>ลดขนาด input (เช่น 480 หรือ 320) ตั้ง "ทุก N เฟรม" หรือจำกัด FPS</td></tr>
<tr><td>Grad-CAM แจ้งว่า gradient เป็นศูนย์</td><td>ลองเลือกชั้นเป้าหมายอื่น (P3 สำหรับวัตถุเล็ก, P5 สำหรับวัตถุใหญ่)</td></tr>
<tr><td>ต้องการดูบันทึกการทำงาน</td><td>เปิด <code>%LOCALAPPDATA%\\VisionModelInspector\\logs\\vmi.log</code></td></tr></table>
</section>""")

    sec.append(f"""
<section><h1><span class="n">15</span>ข้อจำกัดและหมายเหตุสำคัญ</h1>
<ul><li>รองรับเฉพาะงาน Object Detection ของ Ultralytics YOLOv8 และ YOLO11 ที่ทดสอบแล้ว — <b>ไม่ได้รองรับไฟล์ .pt/.onnx ทุกชนิดหรือ YOLO ทุกรุ่น</b>
ตระกูลอื่นอาจตรวจจับได้แต่จะแจ้งว่ายังไม่ได้ทดสอบ และปิด Grad-CAM</li>
<li>Grad-CAM รองรับเฉพาะไฟล์ .pt ของ YOLOv8/YOLO11 (ONNX ยังไม่รองรับ)</li>
<li>แพ็กเกจนี้ใช้ CPU เท่านั้น แพ็กเกจ GPU (CUDA) ต้อง build แยก มีขนาดใหญ่ขึ้นหลาย GB และต้องมีไดรเวอร์ NVIDIA — ยังไม่ได้ทดสอบในรุ่นนี้</li>
<li>การทดสอบกล้องจริง: {facts.get('camera_note', 'ยังไม่ได้ทดสอบกับกล้อง USB จริง (ทดสอบด้วยไฟล์วิดีโอแทน)')}</li>
<li>ตัวติดตั้งยังไม่ได้ลงนามดิจิทัล (code signing)</li>
<li>ค่าความมั่นใจคือ score ของโมเดล ไม่ใช่ค่าความแม่นยำ และจำนวนวัตถุเป็นค่าต่อเฟรม</li></ul>
<h2>สถานะการทดสอบบน Windows</h2>
{facts.get('compat_table_html', '')}
<h1 style="margin-top:10mm"><span class="n">16</span>สัญญาอนุญาตและแหล่งที่มา</h1>
<p>Vision Model Inspector แจกจ่ายภายใต้ <b>GNU AGPL-3.0</b> เนื่องจากรวมไลบรารี Ultralytics (AGPL-3.0)
หากต้องการใช้ในผลิตภัณฑ์ปิดซอร์ส ต้องได้สัญญาอนุญาต Enterprise จาก Ultralytics
ไลบรารีอื่น: PyTorch (BSD-3), PySide6/Qt (LGPL-3.0), OpenCV (Apache-2.0), ONNX Runtime (MIT), NumPy (BSD),
ฟอนต์ IBM Plex Sans Thai (SIL OFL 1.1) — รายละเอียดครบอยู่ในไฟล์ <code>THIRD_PARTY_NOTICES.txt</code> ในโฟลเดอร์ติดตั้ง</p>
<p>โมเดลตัวอย่างที่ใช้ในคู่มือ: yolov8n.pt และ yolo11n.pt จาก github.com/ultralytics/assets (AGPL-3.0)
ภาพตัวอย่าง bus.jpg / zidane.jpg จากแพ็กเกจ Ultralytics</p>
</section>""")

    return f"<!doctype html><html lang='th'><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(sec)}</body></html>"


def main():
    shots, fonts, out = sys.argv[1], sys.argv[2], sys.argv[3]
    facts = {}
    if len(sys.argv) > 4 and os.path.exists(sys.argv[4]):
        with open(sys.argv[4], encoding="utf-8") as f:
            facts = json.load(f)
    log = os.path.join(shots, "screenshots_log.json")
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                facts.setdefault(k, v)
    page = build_html(shots, fonts, facts)
    html_path = os.path.splitext(out)[0] + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(uri(html_path))
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(500)
        footer = ("<div style=\"font-size:8px;width:100%;padding:0 16mm;color:#5F6880;display:flex;"
                  "justify-content:space-between;font-family:sans-serif\"><span>Vision Model Inspector — "
                  "User Manual (TH)</span><span><span class='pageNumber'></span> / <span class='totalPages'>"
                  "</span></span></div>")
        pg.pdf(path=out, format="A4", print_background=True, display_header_footer=True,
               header_template="<div></div>", footer_template=footer, prefer_css_page_size=True)
        b.close()
    print(out)


if __name__ == "__main__":
    main()
