# Vision Model Inspector

โปรแกรม Desktop (Windows 10/11 x64) สำหรับเปิดโมเดลตรวจจับวัตถุที่ผู้ใช้ฝึกไว้ (Ultralytics YOLOv8 / YOLO11 `.pt` และ ONNX)
วิเคราะห์ภาพ วิดีโอ และกล้อง พร้อม Grad-CAM ต่อวัตถุ (detection instance) — UI แบบ C ภาษาไทย

* คู่มือผู้ใช้: `docs/คู่มือการใช้งาน_Vision_Model_Inspector.pdf`
* คู่มือนักพัฒนา / เพิ่ม adapter: `docs/DEVELOPER_TH.md`, `docs/ADAPTERS_TH.md`
* Compatibility matrix และรายงานการทดสอบ: `docs/COMPATIBILITY_TH.md`, `docs/TEST_REPORT_TH.md`

## ดาวน์โหลด

ตัวติดตั้ง Windows x64 (CPU): หน้า Releases ของ repo นี้ → `VisionModelInspector-0.1.0-cpu-setup.exe`
(ทดสอบ: 54/54 เทสผ่าน, ติดตั้ง/รัน/ถอนการติดตั้งบน Windows Server 2022 และ 2025 — ดู `docs/TEST_REPORT_TH.md`)

ภาพหน้าจอจริงอยู่ใน `docs/screenshots/`

## รันจากซอร์ส (นักพัฒนา)

```powershell
py -3.12 -m venv .venv; .venv\Scripts\activate
pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install -r requirements/lock-windows-cpu.txt   # หรือ requirements/runtime.in
python tools/fetch_fonts.py
$env:PYTHONPATH="src"; python -m vmi
```

## สร้างตัวติดตั้ง

ดู `packaging/build_windows.ps1` และ `.github/workflows/build-windows.yml`

## License

AGPL-3.0-or-later (จำเป็นเพราะรวม Ultralytics ซึ่งเป็น AGPL-3.0) — ดู `THIRD_PARTY_NOTICES.txt`
