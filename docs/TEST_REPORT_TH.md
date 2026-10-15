# รายงานการทดสอบและข้อจำกัด — Vision Model Inspector 0.1.0

ทดสอบอัตโนมัติด้วย GitHub Actions (workflow `windows-build-test`, รอบสุดท้าย run 8 วันที่ 15 ต.ค. 2569) ผลดิบของแต่ละรอบอยู่ใน branch
`ci-results/run-<N>` (pytest.txt, junit.xml, ภาพหน้าจอ, JSON ของ self-test, log ของ PyInstaller/Inno Setup)

## สภาพแวดล้อม

| รายการ | ค่า |
|---|---|
| เครื่องทดสอบหลัก | GitHub runner `windows-2022` — Windows Server 2022 Datacenter 10.0.20348, AMD EPYC 9V45 2 คอร์ / 4 threads, RAM 16 GB, ไม่มี GPU, ไม่มีกล้อง |
| เครื่องตรวจตัวติดตั้ง | `windows-2022` และ `windows-2025` (Server 2025, 10.0.26100) — เครื่องใหม่ที่ไม่ได้ติดตั้ง dependency ของโปรเจกต์ |
| Python / ไลบรารี | 3.12.10, PyTorch 2.8.0+cpu, Ultralytics 8.3.253, PySide6 6.9.3, ONNX Runtime 1.31.0, OpenCV 4.14.0, NumPy 2.5.2 |
| โมเดลทดสอบ | `yolov8n.pt`, `yolo11n.pt`, `yolov8n-cls.pt` จาก github.com/ultralytics/assets v8.3.0 (AGPL-3.0) — SHA-256 อยู่ใน `model_hashes.txt` ของผลแต่ละรอบ; `yolov8n.onnx` (export ด้วย Ultralytics), `yolov8n_nonames.onnx` (ลบ metadata), `custom3_untrained.pt` (โครง YOLOv8n 3 คลาสชื่อไทย ไม่ได้ฝึก — ใช้ทดสอบ metadata เท่านั้น) |
| ภาพ/วิดีโอทดสอบ | `bus.jpg`, `zidane.jpg` (จากแพ็กเกจ Ultralytics), `demo.avi` (สร้างจาก bus.jpg) |

## ผลรวม

| รายการ | ผล |
|---|---|
| ชุดเทสอัตโนมัติ (pytest) | **54/54 ผ่าน** (core 26, pipeline 10, models 14, GUI 4) |
| PyInstaller onedir | สำเร็จ (942 MB) |
| Self-test โปรแกรมที่ build แล้ว (path ภาษาไทย `C:\ทดสอบ โมเดล\…`) | ✅ .pt: ตรวจพบ 6 วัตถุ + Grad-CAM (IoU จับคู่ 1.000) / ✅ .onnx: ตรวจพบ 5 วัตถุ, Grad-CAM ปิดตามข้อกำหนด |
| ตัวติดตั้ง Inno Setup | สำเร็จ `VisionModelInspector-0.1.0-cpu-setup.exe` 246,025,841 ไบต์ (~235 MB), SHA-256 `2A6AC5C7B05186055EC4CC9CC2759D905CEE6DA57451A0F0A66A09E7FE4CD82F` (CI run 8, release `v0.1.0-build.8`) — รวมคู่มือ PDF และ THIRD_PARTY_NOTICES |
| ติดตั้งเงียบ → self-test โดย **ตัด Python ออกจาก PATH** → ถอนการติดตั้ง (Server 2022) | ✅ ติดตั้ง/รัน/ถอนสำเร็จ, มี shortcut ใน Start Menu, ไฟล์โปรแกรมถูกลบหลังถอน |
| ติดตั้งบนเครื่องใหม่ Server 2022 และ Server 2025 + self-test YOLO11 + เปิดหน้าจอ | ✅ ทั้งสองระบบ (หมายเหตุ: บน Server 2025 ยังมี `python` alias ของ Windows ใน PATH — โปรแกรมไม่ได้ใช้) |

## รายละเอียดตามเกณฑ์รับงาน (ข้อ 12)

| เกณฑ์ | เทส | ผล |
|---|---|---|
| เปิดโมเดลสองชุดที่ชื่อ/จำนวนคลาสต่างกัน (ไม่ hardcode) | `test_two_models_with_different_classes` (80 คลาส COCO vs 3 คลาสไทย) | ✅ |
| เปลี่ยนโมเดลแล้วคลาส/ตัวกรองเปลี่ยนถูกต้อง, snapshot เก่าไม่ถูกเปลี่ยนป้าย | `test_model_switch_keeps_old_snapshots`, `test_snapshot_keeps_model_identity`, `test_display_store` | ✅ |
| โมเดลไม่มีชื่อคลาส + นำเข้า mapping | `test_onnx_metadata_and_no_names` (class_0…79 → นำเข้า classes.txt) | ✅ |
| mapping ไม่ตรง / ไฟล์เสีย / โมเดลไม่รองรับ | `test_mapping_errors` (7 กรณี รวม YAML ที่พยายามรันคำสั่ง), `test_registry_dispatch_and_unsupported`, `test_classification_model_rejected` | ✅ |
| พิกัดหลัง resize และ letterbox | `test_letterbox_*` (5 รูปทรง), `test_boxes_in_original_coordinates_after_letterbox` (เติมขอบ 120/60 px, ย่อ 50%), `test_onnx_matches_pytorch` | ✅ |
| เลือกวัตถุคลาสเดียวกันคนละชิ้นสำหรับ Grad-CAM | `test_gradcam_same_class_different_instances` — Grad-CAM ให้แผนที่ต่างกัน; HiResCAM ให้ค่าเฉลี่ยในกรอบของวัตถุที่เลือกสูงกว่ากรอบอีกคน | ✅ |
| จับคู่ผลหลัง NMS กับ target ก่อน NMS | `test_gradcam_target_matching_every_detection` — ทุกวัตถุใน bus.jpg: IoU > 0.95, score ต่าง < 0.02 (จริง: 1.000 / 0.000) | ✅ |
| ไม่สร้าง heat map ปลอม | `test_gradcam_layers_never_fake`, `test_gradcam_unmatched_target_is_refused` | ✅ |
| การจับคู่ snapshot กับผลและโมเดล | `test_results_match_their_frame`, `test_snapshot_keeps_model_identity`, GUI full flow | ✅ |
| เลือกกล้องสองอุปกรณ์ | — | ⚠️ **ไม่ได้ทดสอบ** (ไม่มีฮาร์ดแวร์) |
| กล้องหาย/ถูกใช้งานอยู่/เริ่ม-หยุดซ้ำ | `test_bad_sources_report_errors` (index ที่ไม่มีอยู่ + timeout, RTSP เชื่อมต่อไม่ได้ + reconnect จำกัด), `test_video_source_and_repeated_start_stop` (5 รอบ), GUI เริ่ม/หยุดซ้ำ 3 รอบ | ✅ กับ mock/วิดีโอ, ⚠️ ไม่ได้ทดสอบกับกล้องจริง |
| bounded queue, responsiveness, หน่วยความจำต่อเนื่อง | `test_latest_frame_slot_is_bounded`, `test_memory_is_bounded_during_long_run` (1,500 เฟรม 720p: โต < 30 MB), `test_snapshot_store_bounds`, `test_jobs_have_priority_and_pause`, `test_model_swap_waits_for_running_inference` | ✅ |
| ชื่อไฟล์ภาษาไทย การส่งออก การเปิดบน CPU | `test_export_thai_paths_no_overwrite`, `test_imwrite_unicode`, GUI export, self-test path ไทย, `test_cuda_request_without_gpu` | ✅ |
| installer บน Windows ที่ไม่มี Python | ติดตั้งเงียบ + ตัด Python ออกจาก PATH + self-test บน Server 2022/2025 | ✅ (ไม่ใช่ Windows 10/11 เดสก์ท็อปจริง) |

## ประสิทธิภาพที่วัดได้ (CPU 4 threads, ไม่มี GPU)

| งาน | ค่า |
|---|---|
| yolov8n.pt, bus.jpg 810×1080, input 640 | 62–95 ms ต่อภาพ (หลังรอบแรก) |
| yolo11n.pt, bus.jpg | 62–63 ms ต่อภาพ |
| yolov8n.onnx (ONNX Runtime CPU) | 47 ms ต่อภาพ |
| วิดีโอ 960×720 ใน GUI | Capture 25 FPS, Inference 5.7–6.6 FPS (65–90 ms/ภาพ) |
| Grad-CAM ต่อวัตถุ | 0.23–0.42 วินาที |

ตัวเลขเป็นค่าจากเครื่องทดสอบนี้เท่านั้น ไม่รับประกันว่าทุกเครื่องได้ค่าเท่ากัน

## สิ่งที่ยังไม่ได้ทดสอบ / ข้อจำกัด

* **กล้องจริง** (USB, กล้องในเครื่อง, IP/RTSP, กล้องสองตัวพร้อมกัน) — เครื่อง CI ไม่มีกล้อง
* Windows 10/11 **เดสก์ท็อป** จริง และหน้าจอ DPI scaling 125–200% บนจอจริง
* แพ็กเกจ GPU/CUDA — ยังไม่ได้ build
* ONNX layout `(1, A, 4+nc)` และ `(1, N, 6)` — มีโค้ดรองรับแต่ยังไม่มีไฟล์ทดสอบ
* ตัวติดตั้งยังไม่ได้ลงนาม (code signing) — Windows SmartScreen อาจเตือน
* ไม่มีการวัด accuracy/mAP/precision/recall เพราะไม่มีชุดข้อมูล ground truth
