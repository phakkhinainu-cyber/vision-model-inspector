# Compatibility matrix — Vision Model Inspector 0.1.0 (แพ็กเกจ CPU)

สถานะในตารางมาจาก **การทดสอบจริง** ใน GitHub Actions เท่านั้น ช่องที่ไม่ได้ทดสอบระบุไว้ชัดเจน

## ระบบปฏิบัติการ

| ระบบ | สถานะ | หลักฐาน |
|---|---|---|
| Windows Server 2022 (build 20348, kernel ตระกูลเดียวกับ Windows 10 21H2) x64 | ✅ ทดสอบแล้ว: ชุดเทสทั้งหมด, build, ติดตั้งเงียบ, self-test, ถอนการติดตั้ง | CI job `build`, `verify-installer (windows-2022)` |
| Windows Server 2025 (build 26100, kernel ตระกูลเดียวกับ Windows 11 24H2) x64 | ✅ ทดสอบแล้ว: ติดตั้งเงียบ, self-test (YOLO11 + Grad-CAM + หน้าจอ), ถอนการติดตั้ง | CI job `verify-installer (windows-2025)` |
| Windows 11 x64 (เดสก์ท็อป) | ⚠️ คาดว่าใช้ได้ (build เดียวกับ Server 2025) — **ยังไม่ได้ทดสอบบนเครื่องจริง** | — |
| Windows 10 x64 22H2 (เดสก์ท็อป) | ⚠️ คาดว่าใช้ได้ (PyTorch 2.8 / Qt 6.9 รองรับ Windows 10 1809+) — **ยังไม่ได้ทดสอบบนเครื่องจริง** | — |
| Windows ARM64, Windows 32-bit | ❌ นอกขอบเขต | ตัวติดตั้งกำหนด x64 เท่านั้น |

## โมเดล

| โมเดล / ไฟล์ | Inference | Grad-CAM | หมายเหตุ |
|---|---|---|---|
| Ultralytics YOLOv8 detect `.pt` | ✅ | ✅ Grad-CAM + HiResCAM | ทดสอบกับ yolov8n.pt และโมเดล 3 คลาสชื่อไทย |
| Ultralytics YOLO11 detect `.pt` | ✅ | ✅ | ทดสอบกับ yolo11n.pt |
| ONNX ที่ export จาก Ultralytics (YOLOv8/11, output `(1,4+nc,A)`) | ✅ | ❌ ปิดในรุ่นนี้ | มี/ไม่มี metadata ชื่อคลาส ทดสอบทั้งคู่ |
| ONNX `(1,A,4+nc)` และ `(1,N,6)` (รวม NMS) | ⚠️ รองรับในโค้ด ยังไม่มีไฟล์ทดสอบ | ❌ | |
| YOLOv5/v9/v10/12, YOLO26, RT-DETR | ⚠️ อาจรันได้แต่ระบุว่า "ยังไม่ได้ทดสอบ" | ❌ ปิด | |
| segment / pose / classify / obb | ❌ ถูกปฏิเสธพร้อมเหตุผล | ❌ | ทดสอบการปฏิเสธด้วย yolov8n-cls.pt |

เวอร์ชันไลบรารีที่ทดสอบ: Python 3.12.10, PyTorch 2.8.0+cpu, Ultralytics 8.3.253, PySide6 6.9.3,
ONNX Runtime 1.31.0, OpenCV 4.14.0, NumPy 2.5.2 (ทั้งหมดอยู่ใน `requirements/lock-windows-cpu.txt`)

## แหล่งภาพ

| แหล่งภาพ | สถานะ |
|---|---|
| ภาพ JPG/PNG, โฟลเดอร์ภาพ (รวมชื่อไทย/ช่องว่าง) | ✅ ทดสอบแล้ว |
| วิดีโอไฟล์ (AVI/MJPG ทดสอบ; รูปแบบอื่นตามที่ OpenCV FFmpeg รองรับ) | ✅ ทดสอบแล้ว รวมเริ่ม/หยุดซ้ำ |
| กล้อง USB / ในเครื่อง (Qt Multimedia) | ⚠️ **ยังไม่ได้ทดสอบกับกล้องจริง** (CI ไม่มีกล้อง) — ทดสอบได้เฉพาะกรณี "ไม่พบกล้อง" |
| ระบุ index/backend เอง (OpenCV DSHOW/MSMF) | ⚠️ ทดสอบเฉพาะกรณีเปิดไม่สำเร็จ/timeout |
| RTSP | ⚠️ ทดสอบเฉพาะ timeout + reconnect แบบจำกัด (ไม่มีกล้อง IP จริง) |
| กล้องอุตสาหกรรม (GigE/USB3 Vision) | ❌ ต้องมี adapter และ SDK ของผู้ผลิต |

## ฮาร์ดแวร์

| รายการ | ขั้นต่ำ | แนะนำ | หมายเหตุจากการทดสอบ |
|---|---|---|---|
| CPU | x64 4 threads (AVX2) | 8 threads+ | AMD EPYC 4 vCPU: yolov8n 640 ≈ 47–78 ms/ภาพ, Grad-CAM ≈ 0.25 วินาที |
| RAM | 8 GB | 16 GB | ทดสอบบน 16 GB |
| ดิสก์ | ~1.2 GB (ติดตั้ง 942 MB) | | ตัวติดตั้ง ~235 MB |
| GPU | ไม่ต้องมี | — | แพ็กเกจ CUDA ยังไม่ได้ build/ทดสอบ |
| หน้าจอ | 1366×768 | 1920×1080 | ทดสอบเลย์เอาต์ 1366×768 และ 1600×1000 |
