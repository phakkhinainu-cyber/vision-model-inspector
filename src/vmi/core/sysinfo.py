"""Environment / dependency information (recorded in exported metadata)."""
from __future__ import annotations

import hashlib
import platform
import sys
from importlib import metadata


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


_PACKAGES = ("numpy", "opencv-python", "opencv-python-headless", "onnxruntime", "onnxruntime-gpu",
             "torch", "torchvision", "ultralytics", "PySide6", "PyYAML")


def dependency_versions() -> dict:
    out = {"python": sys.version.split()[0], "platform": platform.platform(),
           "machine": platform.machine()}
    for p in _PACKAGES:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    try:  # frozen builds may lack dist-info for some packages
        import cv2
        out.setdefault("opencv", cv2.__version__)
    except Exception:
        pass
    return out


def cuda_status() -> dict:
    """Return {'available': bool, 'name': str, 'reason': str} without raising."""
    try:
        import torch
    except Exception as e:  # torch not installed
        return {"available": False, "name": "", "reason": f"ไม่มี PyTorch: {e}"}
    try:
        if torch.cuda.is_available():
            return {"available": True, "name": torch.cuda.get_device_name(0), "reason": "",
                    "torch_cuda": torch.version.cuda}
        reason = "PyTorch ที่ติดตั้งเป็นรุ่น CPU" if not torch.version.cuda else \
            "ไม่พบ GPU/ไดรเวอร์ NVIDIA ที่ใช้งานได้"
        return {"available": False, "name": "", "reason": reason}
    except Exception as e:
        return {"available": False, "name": "", "reason": str(e)}
