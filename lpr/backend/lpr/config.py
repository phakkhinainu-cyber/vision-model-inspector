"""ตำแหน่งไฟล์ของโปรแกรม (ข้อมูล, log, สำรองข้อมูล, โมเดล, หน้าเว็บ)

ลำดับการเลือกโฟลเดอร์หลัก (LPR_HOME):
1. ตัวแปรแวดล้อม LPR_HOME
2. ไฟล์ชี้ตำแหน่ง (Windows: %ProgramData%\\LPR\\home.txt, อื่นๆ: ~/.config/lpr/home.txt)
3. Windows: D:\\LPR ถ้ามีไดรฟ์ D: แบบฮาร์ดดิสก์ ไม่เช่นนั้น %ProgramData%\\LPR
   macOS/Linux: ~/LPR
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _drive_is_fixed(root: str) -> bool:
    try:
        import ctypes

        return ctypes.windll.kernel32.GetDriveTypeW(root) == 3  # DRIVE_FIXED
    except Exception:  # noqa: BLE001
        return False


def pointer_file() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "LPR" / "home.txt"
    return Path.home() / ".config" / "lpr" / "home.txt"


def default_home() -> Path:
    env = os.environ.get("LPR_HOME")
    if env:
        return Path(env)
    pf = pointer_file()
    try:
        if pf.exists():
            txt = pf.read_text("utf-8").strip()
            if txt:
                return Path(txt)
    except OSError:
        pass
    if os.name == "nt":
        if Path("D:/").exists() and _drive_is_fixed("D:\\"):
            return Path("D:/LPR")
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "LPR"
    return Path.home() / "LPR"


def set_home_pointer(path: Path) -> None:
    """บันทึกตำแหน่งเก็บข้อมูลใหม่ (มีผลเมื่อเปิดโปรแกรมครั้งถัดไป)"""
    pf = pointer_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(str(path), "utf-8")


def app_dir() -> Path:
    """โฟลเดอร์ของตัวโปรแกรม (ตอน build เป็น .exe คือโฟลเดอร์ _internal ของ PyInstaller)"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]  # .../lpr


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def data(self) -> Path:
        return self.home / "data"

    @property
    def db(self) -> Path:
        return self.data / "lpr.db"

    @property
    def images(self) -> Path:
        return self.data / "images"

    @property
    def tmp(self) -> Path:
        return self.data / "tmp"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def backup_default(self) -> Path:
        return self.home / "backup"

    @property
    def user_models(self) -> Path:
        return self.home / "models"

    @property
    def certs(self) -> Path:
        return self.data / "certs"

    @property
    def plate_collect(self) -> Path:
        return self.home / "dataset"

    def ensure(self) -> "Paths":
        for p in (self.data, self.images, self.tmp, self.logs, self.user_models):
            p.mkdir(parents=True, exist_ok=True)
        return self


def bundled_models_dir() -> Path:
    return app_dir() / "models"


def frontend_dist() -> Path:
    for p in (app_dir() / "frontend" / "dist", app_dir() / "web"):
        if (p / "index.html").exists():
            return p
    return app_dir() / "frontend" / "dist"


def resources_dir() -> Path:
    return Path(__file__).resolve().parent / "resources"


MODEL_FILES = {
    "vehicle": "vehicle_yolo11n.onnx",
    "plate": "plate_yolo.onnx",
    "ocr_rec": "th_PP-OCRv5_mobile_rec.onnx",
    "ocr_dict": "th_PP-OCRv5_mobile_rec.dict.txt",
    "ocr_det": "PP-OCRv5_mobile_det.onnx",
}


def find_model(paths: Paths, key: str) -> Path | None:
    """หาไฟล์โมเดล: โฟลเดอร์ models ของผู้ใช้ก่อน (เช่นโมเดลที่ fine-tune เอง) แล้วจึงโมเดลที่มากับโปรแกรม"""
    name = MODEL_FILES[key]
    for d in (paths.user_models, bundled_models_dir()):
        p = d / name
        if p.exists():
            return p
    return None
