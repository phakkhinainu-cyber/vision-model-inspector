# คู่มือนักพัฒนา (สำหรับพัฒนาต่อ)

โปรแกรมนี้สร้างตาม prompt "แบบ 4" ([prompt-แบบ4.md](prompt-แบบ4.md)) ครบทั้ง 6 เฟส —
ตารางท้ายเอกสารสรุปว่าแต่ละข้อของสเปกอยู่ในไฟล์ไหน และอะไรที่ยังควรพัฒนาต่อ

## สถาปัตยกรรม

```
กล้อง RTSP ──► process กล้อง (1 process ต่อกล้อง, multiprocessing spawn)
   sub-stream ─► ตรวจความเคลื่อนไหวใน ROI ─► YOLO11 รถ (ONNX) ─► ByteTrack
   main-stream ─► ring buffer (คลิป) + ภาพความละเอียดสูงสำหรับครอปป้าย
                  └► ตรวจป้าย (YOLO ONNX / classic) ─► ปรับภาพ ─► แยกบรรทัด ─► OCR PP-OCRv5 th (ONNX)
                      ─► แยกวิเคราะห์ป้ายไทย + จังหวัด ─► โหวตหลายเฟรม ─► เหตุการณ์ (ข้ามเส้น / track จบ)
        │ queue (เหตุการณ์ + JPEG, สถานะ, ภาพสด, คลิป)
        ▼
process หลัก (FastAPI/uvicorn)
   CameraManager (watchdog) ─► EventService: กันซ้ำ → สถานะตรวจสอบ → ผูกรถ → visit → บันทึกภาพ → แจ้งเตือน → WebSocket
   Maintenance: สำรองข้อมูล 03:00, ลบภาพ/ข้อมูลเก่า, เตือนดิสก์, รถอยู่เกินเวลา
   SQLite (WAL) ผ่าน SQLAlchemy + Alembic · หน้าเว็บ React (frontend/dist) · PWA service worker
หน้าต่างโปรแกรม: pywebview (Edge WebView2) + tray (pystray) — ถ้ามี service อยู่แล้วจะเปิดแค่ UI
Windows service: WinSW รัน `LPR.exe --server` เป็น LocalSystem เปิดเองตอนบูต รีสตาร์ตเองเมื่อหยุด
```

### ไฟล์สำคัญ

| ส่วน | ไฟล์ |
| --- | --- |
| จุดเริ่มโปรแกรม / CLI | `backend/lpr/__main__.py` (`--server`, `--browser`, `--home`, `--selftest`, `--reset-password`) |
| ตำแหน่งไฟล์ (LPR_HOME) | `backend/lpr/config.py` |
| ค่าตั้งค่าทั้งหมด (schema) | `backend/lpr/settings.py` — เพิ่มค่าใหม่ที่ `DEFS` แล้วหน้าตั้งค่าจะสร้างช่องให้เอง |
| ขั้นตอนต่อกล้อง | `backend/lpr/camera/pipeline.py` (ทดสอบได้โดยไม่ต้องมี process), `worker.py`, `manager.py`, `stream.py`, `clips.py` |
| Vision | `backend/lpr/vision/` — `yolo.py`, `tracker.py`, `plate_detect.py`, `preprocess.py`, `reader.py`, `voting.py`, `motion.py`, `geometry.py`, `ocr/` |
| ป้ายไทย | `backend/lpr/plates/parser.py`, `provinces.py`, `colors.py`, `vehicle_type.py` |
| เหตุการณ์/visit | `backend/lpr/events/service.py`, `visits.py` |
| API | `backend/lpr/api/` — `app.py` (middleware, WebSocket, หน้าเว็บ), `routes_*.py`, `auth.py`, `queries.py` |
| ฐานข้อมูล | `backend/lpr/db/models.py`, `db/migrations/versions/` |
| หน้าเว็บ | `frontend/src/pages/*.tsx`, `components/*.tsx`, `styles.css`, `public/sw.js`, `public/manifest.webmanifest` |
| แพ็กเกจ | `packaging/lpr.spec`, `installer.iss`, `LPR-Service.xml`, `.github/workflows/lpr-build.yml` |

### ฐานข้อมูล

ตาราง: `cameras`, `vehicles` (unique plate_norm+province), `events`, `visits`, `users`, `settings`, `audit_log`
+ `sessions` (ล็อกอิน), `push_subscriptions` (Web Push)
เวลาเก็บเป็น Unix epoch (UTC) แสดงผลเป็น Asia/Bangkok · path ภาพเก็บแบบ relative กับ `<home>/data`
แก้โครงสร้าง: แก้ `models.py` แล้วสร้าง migration ใหม่

```
cd backend
alembic -c <ini ที่ชี้ script_location=lpr/db/migrations และ sqlalchemy.url=sqlite:///...> revision --autogenerate -m "..."
```

โปรแกรมจะ `upgrade head` ให้อัตโนมัติตอนเปิด

### API (ทุก endpoint ต้องล็อกอิน ยกเว้น /api/health และ /api/auth/*)

คำขอที่แก้ไขข้อมูล (POST/PUT/PATCH/DELETE) ต้องมี header `X-LPR: 1` (กัน CSRF) · เอกสาร OpenAPI: `http://127.0.0.1:8765/docs`

| กลุ่ม | endpoint |
| --- | --- |
| ล็อกอิน | `GET /api/auth/status`, `POST /api/auth/setup`, `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/password` |
| เหตุการณ์ | `GET /api/events` (ตัวกรอง: date_from, date_to, q, direction, types, vstatus, cameras, review, vehicle_id, cursor), `GET /api/events/facets`, `GET/PATCH/DELETE /api/events/{id}`, `GET /api/events/{id}/media/{full,plate,thumb,clip}`, `POST /api/events/manual`, `GET /api/review` |
| ส่งออก | `GET /api/export/events.{csv,xlsx,pdf}` (ตัวกรองเดียวกัน) |
| รถ | `GET/POST /api/vehicles`, `GET/PATCH/DELETE /api/vehicles/{id}`, `POST /api/vehicles/from-event/{event_id}`, `GET /api/vehicles/{id}/visits`, `GET /api/visits/inside`, `GET /api/vehicles-export.xlsx`, `POST /api/vehicles-import` |
| กล้อง | `GET/POST /api/cameras`, `PATCH/DELETE /api/cameras/{id}`, `POST /api/cameras/test`, `GET /api/cameras/{id}/snapshot.jpg`, `GET /api/cameras/{id}/live.mjpg`, `POST /api/cameras/{id}/capture`, `POST /api/cameras/{id}/restart` |
| รายงาน | `GET /api/reports/summary`, `GET /api/reports/long-stay` |
| ระบบ | `GET/PUT /api/settings`, `GET/POST/PATCH/DELETE /api/users`, `GET /api/audit`, `POST /api/backup/run`, `GET /api/backup/list`, `POST /api/maintenance/cleanup`, `POST /api/system/storage`, `GET /api/system/status`, `GET /api/push/key`, `POST /api/push/subscribe`, `POST /api/notify/test` |
| สด | `WS /ws` — `event`, `event_update`, `event_delete`, `camera_status`, `alert`, `settings` |

### เพิ่ม OCR engine ใหม่

สร้างคลาสที่มี `name` และ `recognize(line_images: list[np.ndarray]) -> list[tuple[str, float]]`
(ดู `vision/ocr/base.py`, `onnx_ppocr.py`, `engines.py`) แล้วเพิ่มในฟังก์ชัน `create_engine()` และตัวเลือก `ocr_engine`
ใน `settings.py` — engine ที่ fine-tune เองในรูปแบบ PP-OCR ONNX ใช้ได้ทันทีโดยวางไฟล์ไว้ที่ `<home>/models/`

## พัฒนาและทดสอบ

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements/runtime.txt -r requirements/dev.txt     # + desktop.txt ถ้าต้องการหน้าต่าง
python tools/fetch_models.py
cd frontend && npm ci && npm run dev        # หน้าเว็บโหมดพัฒนา http://localhost:5173 (proxy ไป backend)
PYTHONPATH=backend python -m lpr --server --home ./_home     # backend
PYTHONPATH=backend python -m pytest                          # 155 tests
python tools/eval_video.py demo/demo.mp4 --truth demo/demo.json   # ทดสอบทั้ง pipeline กับวิดีโอตัวอย่าง
python tools/make_demo_video.py --images <โฟลเดอร์ภาพรถ> --out demo/demo.mp4  # สร้างวิดีโอตัวอย่างใหม่
```

ชุดทดสอบ: `tests/test_plates.py` (แยกวิเคราะห์ป้าย), `test_provinces.py` (77 จังหวัด + fuzzy), `test_visits.py`
(จับคู่เข้า-ออก), `test_vision_logic.py` (tracker, โหวต, เส้นเสมือน, ROI), `test_pipeline.py` (ทั้ง pipeline กับวิดีโอตัวอย่าง),
`test_api.py` (API ทั้งหมด, สิทธิ์, CSRF, rate limit, ส่งออก, WebSocket)

## Build และเผยแพร่

- push ไปที่ branch → `.github/workflows/lpr-build.yml` สร้าง `LPR-Setup-<ver>.exe` + แบบพกพา Windows/Linux/macOS
  ทดสอบทั้งหมด (pytest, frozen self-test ใน path ภาษาไทย, ติดตั้งจริงเป็น service + เรียก API + ถอนการติดตั้ง)
  แล้วสร้าง GitHub Release `lpr-v<ver>-build.<n>` · ผลทดสอบอยู่ใน branch `ci-results/lpr-run-<n>`
- build เองบน Windows: `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1`
- เปลี่ยนเวอร์ชัน: `backend/lpr/__init__.py`, `pyproject.toml`, `frontend/package.json`, `APP_VERSION` ใน workflow
- สร้างโมเดลใหม่: แก้ `tools/models/build_models.py` แล้ว push (workflow `lpr-models.yml`)

<a id="reset-admin"></a>
### ลืมรหัสผ่าน admin

เปิด Command Prompt แบบ Administrator:

```
"C:\Program Files\LPR\LPR.exe" --reset-password admin รหัสใหม่อย่างน้อย6ตัว
```

(โปรแกรมไม่แสดงข้อความในหน้าต่าง ตรวจผลได้โดยล็อกอินด้วยรหัสใหม่ — รันจากซอร์สจะพิมพ์ผลให้เห็น)

## สถานะตามสเปก (prompt แบบ 4)

| เฟส | สิ่งที่ทำแล้ว | ควรพัฒนาต่อ |
| --- | --- | --- |
| 1 | โครงโปรเจกต์, RTSP + reconnect, ภาพสด (MJPEG), โหมดจำลองด้วยไฟล์วิดีโอ, process ต่อกล้อง + watchdog | — |
| 2 | YOLO11 รถ + ByteTrack, ตรวจป้าย, ปรับภาพ (deskew/CLAHE/sharpen), OCR ไทย PP-OCRv5 (ONNX) + PaddleOCR/EasyOCR สำรอง, โหวตหลายเฟรม, ภาพ/คลิป, กันซ้ำ, กลางคืน/IR, ประเภทรถจาก YOLO+สีป้าย, `eval_accuracy.py`, `collect_plates.py` | ทดสอบกับกล้องและป้ายไทยจริง แล้ว fine-tune (fine-tune.md) |
| 3 | หน้าจอแบบ 4 ครบ: ตัวกรอง, ไทม์ไลน์สด, รายละเอียด, แก้ไข, ส่งออก CSV/Excel/PDF | — |
| 4 | ทะเบียนรถ (+ Excel), กล้อง (วาด ROI/เส้น), รอตรวจสอบ (คีย์บอร์ด), รายงาน, ตั้งค่า, ผู้ใช้, audit log | — |
| 5 | PWA, ล็อกอิน (จำเครื่อง 30 วัน, rate limit), Web Push (VAPID), Telegram, LINE Messaging API, คู่มือ Tailscale + self-signed | — |
| 6 | ตัวติดตั้ง .exe (Inno Setup), Windows service (WinSW), เปิดเองตอนบูต, สำรองข้อมูล, คู่มือภาษาไทย, แบบพกพา Linux/macOS | code signing ตัวติดตั้ง (กันคำเตือน SmartScreen), รุ่นสำหรับการ์ด NVIDIA (onnxruntime-gpu) |

ข้อจำกัดที่ทราบ:
- ความแม่นยำวัดกับภาพรถจริงที่แปะป้ายไทยจำลอง (ยังไม่มีชุดภาพป้ายไทยจริงที่เผยแพร่ได้) — ควรวัดซ้ำด้วยภาพจากกล้องของบ้าน
- ตัวติดตั้งรวม onnxruntime รุ่น CPU (ใช้ได้ทุกเครื่อง) — ถ้ามีการ์ด NVIDIA และต้องการ 4–8 กล้อง ให้รันจากซอร์สแล้ว
  `pip install onnxruntime-gpu` (ระบบเลือก CUDA ให้อัตโนมัติ) หรือ build รุ่น GPU เพิ่มใน workflow
- ตัวติดตั้งยังไม่ได้ลงลายเซ็นดิจิทัล Windows SmartScreen อาจเตือนครั้งแรก (กด More info → Run anyway)
