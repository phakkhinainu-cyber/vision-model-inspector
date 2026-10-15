# PyInstaller spec — onedir build of Vision Model Inspector (Windows x64).
# Build:  pyinstaller --noconfirm packaging/vmi.spec
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

datas = [(os.path.join(SRC, "vmi", "resources"), os.path.join("vmi", "resources"))]
datas += collect_data_files("ultralytics", excludes=["**/assets/*.jpg"])   # model yaml configs
for pkg in ("ultralytics", "torch", "torchvision", "numpy", "opencv-python", "onnxruntime",
            "PySide6", "PyYAML"):
    try:
        datas += copy_metadata(pkg)          # lets the app report dependency versions
    except Exception:
        pass

hiddenimports = collect_submodules("ultralytics", filter=lambda m: not m.startswith(
    ("ultralytics.solutions", "ultralytics.hub", "ultralytics.trackers")))
hiddenimports += collect_submodules("vmi")

a = Analysis(
    [os.path.join(ROOT, "packaging", "launcher.py")],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "IPython", "jupyter", "notebook", "tensorflow", "PyQt5", "PyQt6",
              "pytest", "onnx.reference"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="VisionModelInspector",
    console=False,
    icon=os.path.join(ROOT, "packaging", "app.ico"),
    version=os.path.join(ROOT, "packaging", "version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VisionModelInspector")
