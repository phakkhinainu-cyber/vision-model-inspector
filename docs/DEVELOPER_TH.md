# คู่มือนักพัฒนา — Vision Model Inspector

## สถาปัตยกรรม

```
 แหล่งภาพ (thread ของตัวเอง)          InferenceWorker (thread)             UI (Qt main thread)
 ┌──────────────────────┐  frame   ┌───────────────────────────┐ result ┌──────────────────────┐
 │ QtCameraSource        │────────▶│ LatestFrameSlot (ขนาด 1)   │───────▶│ LiveView: เฟรม + กรอบ │
 │ OpenCVSource (video,  │         │ + คิวงาน snapshot (สำคัญกว่า) │        │ ของเฟรมเดียวกันเท่านั้น │
 │   index, RTSP)        │         │ adapter.predict() ใต้ lock  │        │ SnapshotStore (จำกัด) │
 │ ImageSource           │         └───────────────────────────┘        │ Grad-CAM (QThread)    │
 └──────────────────────┘                     ▲ pause()/resume()        └──────────────────────┘
                                               └──── GradCamThread ─────────────┘
```

* **bounded queue / latest frame**: เฟรมใหม่แทนที่เฟรมที่ยังไม่ได้ประมวลผล (นับเป็น dropped) — RAM ไม่โตตามเวลา
* **frame ID + timestamp** ผูกกับผลทุกครั้ง UI วาดกรอบบนเฟรมที่ใช้คำนวณเท่านั้น
* ตั้ง "ตรวจทุก N เฟรม" และ "สูงสุด X FPS" ได้ แสดง Capture FPS และ Inference FPS แยกกัน
  (เวลาประมวลผล = preprocessing + โมเดล + NMS ต่อภาพ ไม่รวมการแสดงผล)
* **Grad-CAM** พัก live inference ระหว่างคำนวณ (ภาพสดยังแสดง) และใช้ `adapter.lock` ป้องกันการเรียกโมเดลพร้อมกัน
* **เปลี่ยนโมเดล**: `worker.set_adapter(None)` รอ inference ที่กำลังทำให้จบ → `close()` โมเดลเดิม → โหลดใหม่ใน thread
  ผลที่มาจากโมเดลเดิม (hash ไม่ตรง) ถูกทิ้ง snapshot เก่าเก็บชื่อคลาส/hash ของโมเดลเดิมไว้

## โมดูล

| โมดูล | หน้าที่ |
|---|---|
| `core/types.py` | `Detection`, `DetectionResult`, `ModelIdentity`, `InferenceSettings`, `format_confidence` |
| `core/imageops.py` | letterbox แบบเดียวกับ Ultralytics, แปลงพิกัดกลับ, NMS, I/O ชื่อไฟล์ไทย |
| `core/classes.py` | `ClassRegistry`, อ่าน data.yaml/classes.txt/JSON (safe_load / literal_eval), ชื่อแสดงผล |
| `core/snapshots.py` | `Snapshot`, `SnapshotStore` (จำกัดจำนวนและ MB) |
| `core/export.py` | ส่งออก PNG/CSV/JSON ไม่เขียนทับ |
| `adapters/*` | โมเดล (ดู `ADAPTERS_TH.md`) |
| `gradcam/*` | Grad-CAM |
| `sources/*` | กล้อง วิดีโอ ภาพ, credential |
| `pipeline/inference_worker.py` | thread inference |
| `ui/*` | หน้าจอ PySide6 |
| `config.py` | ตำแหน่งไฟล์ผู้ใช้ (`%LOCALAPPDATA%\VisionModelInspector`), settings.json, log พร้อม redaction |
| `selftest.py` | โหมดทดสอบอัตโนมัติสำหรับ build ที่ freeze แล้ว |

## รันและทดสอบ

```powershell
py -3.12 -m venv .venv; .venv\Scripts\activate
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements\lock-windows-cpu.txt
python tools\fetch_fonts.py
# ดาวน์โหลดโมเดลตัวอย่างทางการของ Ultralytics (AGPL-3.0)
mkdir test_assets\models
curl.exe -L -o test_assets\models\yolov8n.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
curl.exe -L -o test_assets\models\yolo11n.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
python tools\make_test_assets.py
python -m pytest -v
$env:PYTHONPATH="src"; python -m vmi
```

`tools/screenshots.py <โฟลเดอร์>` ขับโปรแกรมจริงและบันทึกภาพหน้าจอ (ใช้ทำคู่มือ)

Self-test ของ build ที่ติดตั้งแล้ว (ไม่ต้องมี Python):

```
"VisionModelInspector.exe" --selftest --model yolov8n.pt --image bus.jpg --out result.json --screenshot ui.png
```

## Build / ตัวติดตั้ง

* `packaging/vmi.spec` — PyInstaller onedir (รวม Python runtime, PyTorch CPU, PySide6, ONNX Runtime, ฟอนต์)
* `packaging/installer.iss` — Inno Setup 6: ติดตั้งแบบผู้ใช้ปัจจุบัน (ไม่ต้องเป็น admin) หรือทุกผู้ใช้, shortcut, uninstall
* `packaging/build_windows.ps1` — build บนเครื่อง Windows
* `.github/workflows/build-windows.yml` — CI: ทดสอบ → ภาพหน้าจอ → PyInstaller → self-test (path ภาษาไทย)
  → installer → ติดตั้งเงียบ/ทดสอบ/ถอนการติดตั้ง → ตรวจบน Windows Server 2022 และ 2025

### แพ็กเกจ GPU (CUDA)
แพ็กเกจหลักเป็น CPU (ขนาดเล็กกว่ามาก และไม่ต้องมี GPU) หากต้องการ GPU ให้ build แยก:
```powershell
pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision
pip install onnxruntime-gpu   # แทน onnxruntime
```
ข้อกำหนดเครื่องผู้ใช้: การ์ด NVIDIA + ไดรเวอร์ที่รองรับ CUDA รุ่นของ wheel (โปรแกรมไม่ติดตั้งไดรเวอร์ให้)
ขนาดตัวติดตั้งจะใหญ่ขึ้นหลาย GB — ยังไม่ได้ build/ทดสอบใน CI รุ่นนี้

## ความปลอดภัย / ความเป็นส่วนตัว
* `.pt` โหลดผ่าน pickle → ยืนยันกับผู้ใช้ก่อนโหลด (จำ SHA-256 ที่เชื่อถือได้)
* ปิด auto-install / การเชื่อมต่อออนไลน์ของ Ultralytics (`YOLO_OFFLINE`, `YOLO_AUTOINSTALL=False`)
* ไม่มีการส่งภาพ/โมเดลออกภายนอก ไม่บันทึกทุกเฟรมอัตโนมัติ
* รหัสผ่าน RTSP: เข้ารหัสด้วย Windows DPAPI หรือไม่บันทึกเลย, log ผ่าน `RedactingFilter`
