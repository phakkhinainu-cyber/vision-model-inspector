"""User-writable paths, persistent settings and logging (with credential redaction)."""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import sys
from dataclasses import dataclass, field, asdict

from . import APP_ID

log = logging.getLogger("vmi")


def user_data_dir() -> str:
    """%LOCALAPPDATA%\\VisionModelInspector on Windows, ~/.local/share/… elsewhere.

    Can be overridden with the VMI_DATA_DIR environment variable (tests, portable use).
    """
    override = os.environ.get("VMI_DATA_DIR")
    if override:
        base = override
    elif sys.platform == "win32":
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_ID)
    else:
        base = os.path.join(os.environ.get("XDG_DATA_HOME") or
                            os.path.expanduser("~/.local/share"), APP_ID)
    os.makedirs(base, exist_ok=True)
    return base


def resource_path(*parts) -> str:
    """Locate bundled resources both in source checkouts and PyInstaller builds."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cand = os.path.join(base, "vmi", "resources", *parts)
        if os.path.exists(cand):
            return cand
    return os.path.join(os.path.dirname(__file__), "resources", *parts)


# ---------------------------------------------------------------- logging
_URL_CRED = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/@\s:]+)(:[^/@\s]*)?@")
_PWD_KV = re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+")


def redact(text: str) -> str:
    text = _URL_CRED.sub(lambda m: f"{m.group(1)}***:***@", text)
    return _PWD_KV.sub(lambda m: f"{m.group(1)}=***", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        red = redact(msg)
        if red != msg:
            record.msg, record.args = red, ()
        return True


def setup_logging(level=logging.INFO) -> str:
    log_dir = os.path.join(user_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "vmi.log")
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(RedactingFilter())
    root.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.addFilter(RedactingFilter())
        root.addHandler(sh)
    return path


# ---------------------------------------------------------------- settings
@dataclass
class AppSettings:
    conf: float = 0.25
    iou: float = 0.45
    imgsz: int = 640
    device: str = "auto"
    heatmap_opacity: float = 0.5
    infer_every_n: int = 1
    max_infer_fps: float = 15.0
    snapshot_max_items: int = 30
    snapshot_max_mb: int = 512
    recent_models: list = field(default_factory=list)
    trusted_model_hashes: list = field(default_factory=list)
    preferred_camera: dict = field(default_factory=dict)   # {"kind","id","name",...}
    ip_cameras: list = field(default_factory=list)          # [{"name","url","user","secret"}]
    last_export_dir: str = ""
    last_open_dir: str = ""
    sync_views: bool = True

    @staticmethod
    def path() -> str:
        return os.path.join(user_data_dir(), "settings.json")

    @classmethod
    def load(cls) -> "AppSettings":
        try:
            with open(cls.path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        try:
            return cls(**known)
        except TypeError:
            return cls()

    def save(self):
        p = self.path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)

    def add_recent_model(self, path: str, limit: int = 8):
        path = os.path.abspath(path)
        self.recent_models = [path] + [p for p in self.recent_models if p != path]
        self.recent_models = self.recent_models[:limit]
