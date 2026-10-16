# ไลเซนส์ของไลบรารี โมเดล และไฟล์ที่ใช้

ตัวโปรแกรม LPR บ้าน เผยแพร่ภายใต้ **GNU AGPL-3.0-or-later** (ไฟล์ `LICENSE`)
เหตุผล: ใช้โมเดล YOLO11 ของ Ultralytics (AGPL-3.0) และโมเดลตรวจจับป้ายที่ฝึกจาก Ultralytics (AGPL-3.0)
ถ้าต้องการใช้เชิงพาณิชย์แบบไม่เปิดซอร์ส ต้องซื้อ Ultralytics Enterprise License หรือเปลี่ยนเป็นโมเดลที่ไลเซนส์อนุญาต
(เช่นโมเดลตรวจจับป้ายไทย HurricaneOD ของ Rattatammanoon ซึ่งเป็น Apache-2.0 — ดู fine-tune.md)

รายการไลเซนส์ฉบับเต็มของทุกแพ็กเกจ Python ที่อยู่ในตัวติดตั้ง สร้างอัตโนมัติตอน build ไว้ที่ `THIRD_PARTY_NOTICES.txt`

## Backend (Python)

| ไลบรารี | ใช้ทำอะไร | ไลเซนส์ |
| --- | --- | --- |
| Python 3.12 | ภาษา/ตัวแปลภาษา (ฝังในตัวติดตั้ง) | PSF License |
| FastAPI | REST API + WebSocket | MIT |
| Starlette | เว็บเฟรมเวิร์กที่ FastAPI ใช้ | BSD-3-Clause |
| Uvicorn (+ websockets, httptools, uvloop, watchfiles) | web server | BSD-3-Clause / MIT / Apache-2.0 |
| Pydantic | ตรวจข้อมูล | MIT |
| python-multipart | อัปโหลดไฟล์ Excel | Apache-2.0 |
| SQLAlchemy | ฐานข้อมูล | MIT |
| Alembic | อัปเกรดโครงสร้างฐานข้อมูล | MIT |
| SQLite | ฐานข้อมูลในเครื่อง (โหมด WAL) | Public Domain |
| OpenCV (opencv-python-headless) | อ่าน RTSP/วิดีโอ, ประมวลผลภาพ, เขียนคลิป WebM (FFmpeg LGPL + libvpx BSD) | Apache-2.0 (OpenCV), LGPL-2.1 (FFmpeg) |
| NumPy | คำนวณ | BSD-3-Clause |
| ONNX Runtime (`onnxruntime`; รุ่น GPU ใช้ `onnxruntime-directml`) | รันโมเดลบน CPU / DirectML / CUDA | MIT |
| DirectML (`DirectML.dll`, Microsoft) — เฉพาะรุ่น GPU | ใช้การ์ดจอผ่าน DirectX 12 (มากับ onnxruntime-directml) | Microsoft DirectML redistributable license |
| RapidFuzz | จับคู่ชื่อจังหวัด | MIT |
| argon2-cffi | เข้ารหัสรหัสผ่านผู้ใช้ | MIT |
| cryptography | VAPID, self-signed certificate, เข้ารหัสสำรอง | Apache-2.0 / BSD-3-Clause |
| keyring (+ pywin32-ctypes) | เก็บรหัสผ่านกล้องใน Windows Credential Manager | MIT / BSD-3-Clause |
| openpyxl | ส่งออก/นำเข้า Excel | MIT |
| fpdf2 | สร้างรายงาน PDF | LGPL-3.0 |
| uharfbuzz (HarfBuzz) | จัดวางสระ/วรรณยุกต์ไทยใน PDF | Apache-2.0 (uharfbuzz), MIT (HarfBuzz) |
| httpx | ส่ง Telegram / LINE | BSD-3-Clause |
| pywebpush, py-vapid, http-ece | Web Push | MPL-2.0 |
| Pillow | ไอคอน, ภาพ | MIT-CMU (HPND) |
| tzdata | เขตเวลา Asia/Bangkok บน Windows | Apache-2.0 |
| pywebview (+ pythonnet บน Windows) | หน้าต่างโปรแกรม (Edge WebView2) | BSD-3-Clause / MIT |
| pystray | ไอคอนที่ system tray | LGPL-3.0 |

ทางเลือก (ไม่ได้อยู่ในตัวติดตั้ง ติดตั้งเองเมื่อรันจากซอร์ส):

| ไลบรารี | ใช้ทำอะไร | ไลเซนส์ |
| --- | --- | --- |
| PaddleOCR + PaddlePaddle | OCR engine ทางเลือก / ฝึกโมเดล OCR | Apache-2.0 |
| EasyOCR (+ PyTorch) | OCR engine สำรอง ('th','en') | Apache-2.0 / BSD-3-Clause |
| Ultralytics | ฝึกโมเดลตรวจจับป้าย, ส่งออก ONNX | AGPL-3.0 |
| paddle2onnx | แปลงโมเดล PaddleOCR เป็น ONNX | Apache-2.0 |

เครื่องมือ build: PyInstaller (GPL-2.0 with bootloader exception — ไม่กระทบไลเซนส์ของโปรแกรม), Inno Setup (Inno Setup License),
WinSW (MIT) สำหรับ Windows service, pip-licenses (MIT), pytest (MIT)

## Frontend (JavaScript)

| ไลบรารี | ไลเซนส์ |
| --- | --- |
| React, React DOM | MIT |
| React Router | MIT |
| Vite, @vitejs/plugin-react, TypeScript | MIT / Apache-2.0 |
| @fontsource/anuphan, @fontsource/sarabun, @fontsource/jetbrains-mono (ไฟล์ฟอนต์) | SIL Open Font License 1.1 (โค้ดแพ็กเกจ MIT) |

ไอคอนในโปรแกรมวาดเองเป็น SVG (ไม่มีไลเซนส์ภายนอก)

## ฟอนต์

| ฟอนต์ | ใช้ที่ | ไลเซนส์ |
| --- | --- | --- |
| Anuphan (Cadson Demak) | ข้อความบนหน้าจอ | SIL OFL 1.1 |
| Sarabun (Cadson Demak) | ป้ายทะเบียน, รายงาน PDF, ไอคอน | SIL OFL 1.1 (`backend/lpr/resources/fonts/Sarabun-OFL.txt`) |
| JetBrains Mono (JetBrains) | เวลา | SIL OFL 1.1 |

ฟอนต์ทั้งหมดฝังอยู่ในโปรแกรม ไม่โหลดจากอินเทอร์เน็ต

## โมเดล

| ไฟล์ | ที่มา | ไลเซนส์ |
| --- | --- | --- |
| `vehicle_yolo11n.onnx` | Ultralytics YOLO11n (COCO) ส่งออกเป็น ONNX | AGPL-3.0 |
| `plate_yolo.onnx` | morsetechlab/yolov11-license-plate-detection (license-plate-finetune-v1n) | AGPL-3.0 |
| `th_PP-OCRv5_mobile_rec.onnx` + `.dict.txt` | PaddleOCR th_PP-OCRv5_mobile_rec แปลงด้วย paddle2onnx | Apache-2.0 |
| `PP-OCRv5_mobile_det.onnx` | PaddleOCR PP-OCRv5_mobile_det แปลงด้วย paddle2onnx | Apache-2.0 |

สร้างซ้ำได้ด้วย `.github/workflows/lpr-models.yml` (`tools/models/build_models.py`) — ค่า sha256 อยู่ใน `models/manifest.json`

## ข้อมูลตัวอย่าง

วิดีโอตัวอย่าง `demo/demo.mp4` ใช้ภาพรถจากชุดข้อมูล keremberke/license-plate-object-detection (Roboflow) ภายใต้ **CC BY 4.0**
โดยแทนที่ป้ายเดิมด้วยป้ายทะเบียนไทยที่สร้างขึ้นเอง (ไม่ใช่ทะเบียนจริง) — รายละเอียดใน `demo/ATTRIBUTION.txt`
