#!/usr/bin/env bash
# เปิดโปรแกรมจากซอร์สบน macOS / Linux (ต้องมี Python 3.11+ และ Node.js 20+ สำหรับ build หน้าเว็บครั้งแรก)
#   ./scripts/start.sh            เปิดหน้าต่าง/เบราว์เซอร์
#   ./scripts/start.sh --server   รันเฉพาะระบบเบื้องหลัง (เช่นบน Linux ที่ไม่มีหน้าจอ แล้วเปิดดูจากมือถือ)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if [ ! -x .venv/bin/python ]; then
  echo "[LPR] กำลังสร้างสภาพแวดล้อม Python ..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements/runtime.txt
  .venv/bin/python -m pip install -r requirements/desktop.txt || echo "[LPR] ไม่มีหน้าต่างโปรแกรม จะเปิดผ่านเบราว์เซอร์แทน"
fi
[ -f models/vehicle_yolo11n.onnx ] || .venv/bin/python tools/fetch_models.py
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci && npm run build)
fi
export PYTHONPATH="$PWD/backend"
exec .venv/bin/python -m lpr "$@"
