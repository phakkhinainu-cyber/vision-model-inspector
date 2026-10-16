@echo off
rem เปิดโปรแกรมจากซอร์สบน Windows (ใช้เมื่อไม่ได้ติดตั้งด้วย LPR-Setup.exe)
rem ต้องมี Python 3.11 ขึ้นไป (https://www.python.org/downloads/) ครั้งแรกจะติดตั้งไลบรารีและดาวน์โหลดโมเดลให้อัตโนมัติ
chcp 65001 >nul
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (
  echo [LPR] กำลังสร้างสภาพแวดล้อม Python ...
  py -3 -m venv .venv || python -m venv .venv || (echo ไม่พบ Python กรุณาติดตั้ง Python 3.11+ & pause & exit /b 1)
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements\runtime.txt -r requirements\desktop.txt || (pause & exit /b 1)
)
if not exist models\vehicle_yolo11n.onnx .venv\Scripts\python tools\fetch_models.py
if not exist frontend\dist\index.html (
  echo [LPR] ยังไม่มีหน้าเว็บ กำลัง build (ต้องมี Node.js 20+) ...
  pushd frontend & call npm ci & call npm run build & popd
)
set PYTHONPATH=%CD%\backend
.venv\Scripts\python -m lpr %*
