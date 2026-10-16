# PyInstaller spec — LPR บ้าน (Windows x64, onedir)
# Build: pyinstaller --noconfirm --clean packaging/lpr.spec   (ต้อง build หน้าเว็บและมีไฟล์โมเดลใน models/ ก่อน)
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(ROOT, "backend")

datas = [
    (os.path.join(ROOT, "frontend", "dist"), os.path.join("frontend", "dist")),
    (os.path.join(ROOT, "models"), "models"),
    (os.path.join(ROOT, "demo"), "demo"),
    (os.path.join(BACKEND, "lpr", "resources"), os.path.join("lpr", "resources")),
    (os.path.join(BACKEND, "lpr", "db", "migrations"), os.path.join("lpr", "db", "migrations")),
]
for pkg in ("keyring", "fastapi", "starlette", "uvicorn", "pywebpush", "py-vapid", "onnxruntime", "onnxruntime-directml",
            "onnxruntime-gpu", "opencv-python-headless",
            "sqlalchemy", "alembic", "fpdf2", "pywebview", "pystray"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass
for pkg in ("alembic", "webview"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

hiddenimports = collect_submodules("lpr")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("keyring.backends")
hiddenimports += ["pystray._win32", "webview.platforms.edgechromium", "webview.platforms.winforms",
                  "sqlalchemy.dialects.sqlite", "argon2", "_cffi_backend", "uharfbuzz", "openpyxl", "httpx",
                  "multipart", "python_multipart", "tzdata"]

# DLL ของ onnxruntime ทุกแบบ (CPU / DirectML.dll ของรุ่น GPU / provider ของ CUDA)
binaries = collect_dynamic_libs("onnxruntime")

a = Analysis(
    [os.path.join(ROOT, "packaging", "launcher.py")],
    pathex=[BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "IPython", "jupyter", "notebook", "matplotlib", "torch", "tensorflow", "paddle", "easyocr",
              "pytest", "PyQt5", "PyQt6", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="LPR",
    console=False,
    icon=os.path.join(ROOT, "packaging", "app.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LPR")
