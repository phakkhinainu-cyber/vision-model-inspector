"""ค่าตั้งค่าทั้งหมดของโปรแกรม (ปรับได้จากหน้า ตั้งค่า ไม่มีการ hard-code)

แต่ละค่ามีชนิด, ค่าเริ่มต้น, ชื่อภาษาไทย และกลุ่ม เพื่อให้หน้าเว็บสร้างแบบฟอร์มได้เอง
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from sqlalchemy import select

from .db.models import Setting
from .db.session import Database


@dataclass(frozen=True)
class SettingDef:
    key: str
    type: str  # int | float | bool | str | select | time | path | secret | text
    default: Any
    label: str
    group: str
    help: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple[str, ...] = field(default_factory=tuple)
    restart: bool = False  # ต้องรีสตาร์ตโปรแกรมจึงมีผล
    cameras: bool = False  # ต้องรีสตาร์ต process กล้อง (ทำให้อัตโนมัติ)
    secret: bool = False


G_GENERAL = "ทั่วไป"
G_CAPTURE = "การจับภาพและอ่านป้าย"
G_VISIT = "การเข้า-ออก"
G_STORAGE = "การเก็บข้อมูลและสำรองข้อมูล"
G_NOTIFY = "การแจ้งเตือน"
G_SERVER = "เครือข่ายและความปลอดภัย"

DEFS: tuple[SettingDef, ...] = (
    SettingDef("house_name", "str", "บ้านของฉัน", "ชื่อบ้าน/ที่อยู่ที่แสดงบนหน้าจอ", G_GENERAL),
    SettingDef("review_threshold", "float", 0.80, "เกณฑ์ความมั่นใจ (ต่ำกว่านี้ = รอตรวจสอบ)", G_CAPTURE,
               min=0.3, max=0.99, step=0.01),
    SettingDef("review_if_no_province", "bool", True, "อ่านจังหวัดไม่ได้ให้ รอตรวจสอบ", G_CAPTURE),
    SettingDef("dedup_seconds", "int", 60, "กันบันทึกซ้ำ: ป้ายเดียวกัน กล้องเดียวกัน ภายใน (วินาที)", G_CAPTURE,
               min=0, max=3600),
    SettingDef("dedup_unread_seconds", "int", 15, "กันบันทึกซ้ำรถที่อ่านป้ายไม่ได้ ภายใน (วินาที)", G_CAPTURE,
               min=0, max=600),
    SettingDef("province_min_score", "int", 80, "คะแนนขั้นต่ำการจับคู่ชื่อจังหวัด (0-100)", G_CAPTURE,
               min=50, max=100, cameras=True),
    SettingDef("detect_fps", "float", 8.0, "จำนวนเฟรมที่ตรวจจับต่อวินาทีเมื่อมีความเคลื่อนไหว", G_CAPTURE,
               min=1, max=20, step=0.5, cameras=True),
    SettingDef("vehicle_conf", "float", 0.35, "ความไวการตรวจจับรถ (ค่าน้อย = ไวขึ้น)", G_CAPTURE,
               min=0.1, max=0.9, step=0.01, cameras=True),
    SettingDef("plate_conf", "float", 0.30, "ความไวการตรวจจับป้าย", G_CAPTURE, min=0.05, max=0.9, step=0.01,
               cameras=True),
    SettingDef("motion_threshold", "float", 0.004, "ความไวการตรวจความเคลื่อนไหว (สัดส่วนพื้นที่ที่เปลี่ยน)",
               G_CAPTURE, min=0.0005, max=0.1, step=0.0005, cameras=True),
    SettingDef("motion_hold_seconds", "float", 3.0, "ตรวจจับต่ออีกกี่วินาทีหลังความเคลื่อนไหวหยุด", G_CAPTURE,
               min=0.5, max=30, step=0.5, cameras=True),
    SettingDef("vote_min_frames", "int", 5, "จำนวนเฟรมขั้นต่ำที่ใช้โหวตผลป้าย", G_CAPTURE, min=1, max=15,
               cameras=True),
    SettingDef("vote_max_frames", "int", 15, "จำนวนเฟรมสูงสุดที่เก็บไว้โหวต (เลือกเฟรมป้ายคมที่สุด)", G_CAPTURE,
               min=3, max=40, cameras=True),
    SettingDef("crossing_wait_seconds", "float", 1.0,
               "หลังรถข้ามเส้น รอเก็บเฟรมเพิ่มสูงสุดกี่วินาทีก่อนบันทึก", G_CAPTURE, min=0, max=5, step=0.1,
               cameras=True),
    SettingDef("emit_on_track_end", "bool", True, "บันทึกเมื่อรถหายจากภาพ แม้ไม่ข้ามเส้น", G_CAPTURE,
               cameras=True),
    SettingDef("min_track_movement", "float", 0.04, "ระยะเคลื่อนที่ขั้นต่ำของรถ (สัดส่วนของภาพ) จึงนับเป็นรถผ่าน",
               G_CAPTURE, min=0, max=0.5, step=0.01, cameras=True),
    SettingDef("track_timeout_seconds", "float", 2.5, "ถือว่ารถออกจากภาพเมื่อไม่เห็นนานกี่วินาที", G_CAPTURE,
               min=0.5, max=20, step=0.5, cameras=True),
    SettingDef("night_brightness", "int", 70, "ความสว่างเฉลี่ยต่ำกว่านี้ = โหมดกลางคืน (0-255)", G_CAPTURE,
               min=10, max=200, cameras=True),
    SettingDef("clip_enabled", "bool", True, "บันทึกคลิปสั้นของแต่ละเหตุการณ์", G_CAPTURE, cameras=True),
    SettingDef("clip_pre_seconds", "float", 3.0, "คลิป: เริ่มก่อนเหตุการณ์ (วินาที)", G_CAPTURE, min=0, max=10,
               step=0.5, cameras=True),
    SettingDef("clip_post_seconds", "float", 5.0, "คลิป: หลังเหตุการณ์ (วินาที)", G_CAPTURE, min=0, max=15,
               step=0.5, cameras=True),
    SettingDef("clip_fps", "int", 10, "คลิป: เฟรมต่อวินาที", G_CAPTURE, min=2, max=25, cameras=True),
    SettingDef("ocr_engine", "select", "auto", "OCR engine", G_CAPTURE,
               options=("auto", "onnx", "paddle", "easyocr"),
               help="auto = PP-OCRv5 ภาษาไทยผ่าน ONNX Runtime ถ้าไม่มีจะลอง PaddleOCR แล้ว EasyOCR", cameras=True),
    SettingDef("device", "select", "auto", "อุปกรณ์ประมวลผลโมเดล", G_CAPTURE, options=("auto", "cpu", "cuda", "dml"),
               help="auto = ใช้การ์ด NVIDIA (CUDA) หรือ DirectML ถ้ามี ไม่เช่นนั้นใช้ CPU", cameras=True),
    SettingDef("collect_plates", "bool", False, "เก็บภาพป้ายไว้ฝึกโมเดล (โฟลเดอร์ dataset)", G_CAPTURE, cameras=True),
    SettingDef("overstay_hours", "float", 24.0, "เข้าแล้วไม่ออกเกิน (ชั่วโมง) = ไม่พบการออก", G_VISIT, min=1,
               max=720),
    SettingDef("long_stay_alert_hours", "float", 12.0, "แจ้งเตือนเมื่อรถ ไม่รู้จัก/เฝ้าระวัง อยู่เกิน (ชั่วโมง)",
               G_VISIT, min=0.5, max=720),
    SettingDef("image_retention_days", "int", 90, "ลบภาพที่เก่ากว่า (วัน)", G_STORAGE, min=1, max=3650),
    SettingDef("row_retention_days", "int", 365, "เก็บข้อมูลแถวไว้ (วัน)", G_STORAGE, min=7, max=36500),
    SettingDef("backup_dir", "path", "", "โฟลเดอร์สำรองฐานข้อมูล (ว่าง = <ที่เก็บข้อมูล>\\backup)", G_STORAGE),
    SettingDef("backup_time", "time", "03:00", "เวลาสำรองข้อมูลอัตโนมัติทุกวัน", G_STORAGE),
    SettingDef("backup_keep", "int", 14, "เก็บชุดสำรองย้อนหลัง (ชุด)", G_STORAGE, min=1, max=365),
    SettingDef("disk_warn_percent", "int", 10, "แจ้งเตือนเมื่อพื้นที่ดิสก์เหลือน้อยกว่า (%)", G_STORAGE, min=1,
               max=50),
    SettingDef("notify_unknown", "bool", True, "แจ้งเตือนเมื่อพบรถ ไม่รู้จัก", G_NOTIFY),
    SettingDef("notify_watch", "bool", True, "แจ้งเตือนเมื่อพบรถ เฝ้าระวัง", G_NOTIFY),
    SettingDef("notify_overstay", "bool", True, "แจ้งเตือนเมื่อรถอยู่เกินเวลาที่ตั้ง", G_NOTIFY),
    SettingDef("notify_unread", "bool", False, "แจ้งเตือนเมื่ออ่านป้ายไม่ได้", G_NOTIFY),
    SettingDef("webpush_enabled", "bool", True, "Web Push (แจ้งเตือนบนมือถือ/แท็บเล็ตที่ติดตั้งแอป)", G_NOTIFY),
    SettingDef("telegram_enabled", "bool", False, "Telegram Bot", G_NOTIFY),
    SettingDef("telegram_token", "secret", "", "Telegram: Bot token", G_NOTIFY, secret=True),
    SettingDef("telegram_chat_id", "str", "", "Telegram: chat id", G_NOTIFY),
    SettingDef("line_enabled", "bool", False, "LINE Messaging API (ไม่ใช่ LINE Notify ที่ปิดบริการแล้ว)", G_NOTIFY),
    SettingDef("line_token", "secret", "", "LINE: Channel access token", G_NOTIFY, secret=True),
    SettingDef("line_to", "str", "", "LINE: user id หรือ group id ที่จะส่งถึง", G_NOTIFY),
    SettingDef("port", "int", 8765, "พอร์ตเว็บ (ในวง LAN)", G_SERVER, min=1024, max=65535, restart=True),
    SettingDef("bind_lan", "bool", True, "เปิดให้มือถือ/แท็บเล็ตในวง LAN เข้าถึง", G_SERVER, restart=True,
               help="ปิด = เข้าได้จากคอมเครื่องนี้และผ่าน Tailscale serve เท่านั้น"),
    SettingDef("https_selfsigned", "bool", False, "เปิด HTTPS ในบ้านด้วย self-signed certificate", G_SERVER,
               restart=True),
    SettingDef("https_port", "int", 8766, "พอร์ต HTTPS (self-signed)", G_SERVER, min=1024, max=65535, restart=True),
    SettingDef("remember_days", "int", 30, "จำเครื่องที่ล็อกอิน (วัน)", G_SERVER, min=1, max=365),
    SettingDef("login_max_attempts", "int", 5, "ล็อกอินผิดได้กี่ครั้งก่อนล็อก", G_SERVER, min=3, max=20),
    SettingDef("login_lock_minutes", "int", 15, "ล็อกการเข้าสู่ระบบ (นาที)", G_SERVER, min=1, max=1440),
)
DEF_BY_KEY = {d.key: d for d in DEFS}
# ค่าที่ระบบเก็บเอง (ไม่แสดงในหน้าตั้งค่า)
INTERNAL_KEYS = ("vapid_private_pem", "vapid_public_b64", "secret_fallback_key")


def coerce(d: SettingDef, value: Any) -> Any:
    if d.type == "int":
        v: Any = int(float(value))
    elif d.type == "float":
        v = float(value)
    elif d.type == "bool":
        v = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
    elif d.type == "select":
        v = str(value)
        if d.options and v not in d.options:
            raise ValueError(f"{d.label}: ค่าไม่ถูกต้อง")
    elif d.type == "time":
        v = str(value)
        hh, mm = v.split(":")
        if not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError(f"{d.label}: เวลาไม่ถูกต้อง")
        v = f"{int(hh):02d}:{int(mm):02d}"
    else:
        v = "" if value is None else str(value)
    if d.type in ("int", "float"):
        if d.min is not None and v < d.min:
            raise ValueError(f"{d.label}: ต้องไม่น้อยกว่า {d.min:g}")
        if d.max is not None and v > d.max:
            raise ValueError(f"{d.label}: ต้องไม่มากกว่า {d.max:g}")
    return v


class SettingsStore:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self.reload()

    def reload(self) -> None:
        with self.db.session() as s:
            rows = {r.key: r.value for r in s.scalars(select(Setting))}
        vals: dict[str, Any] = {}
        for d in DEFS:
            if d.key in rows:
                try:
                    vals[d.key] = coerce(d, json.loads(rows[d.key]))
                    continue
                except Exception:  # noqa: BLE001
                    pass
            vals[d.key] = d.default
        for k in INTERNAL_KEYS:
            if k in rows:
                vals[k] = json.loads(rows[k])
        with self._lock:
            self._cache = vals

    def get(self, key: str) -> Any:
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        d = DEF_BY_KEY.get(key)
        return d.default if d else None

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._cache)

    def on_change(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(fn)

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        """ตรวจค่าแล้วบันทึก คืนค่าที่เปลี่ยนจริง"""
        clean: dict[str, Any] = {}
        for k, v in changes.items():
            if k in INTERNAL_KEYS:
                clean[k] = v
                continue
            d = DEF_BY_KEY.get(k)
            if d is None:
                raise ValueError(f"ไม่รู้จักค่าตั้งค่า {k}")
            if d.secret and v in ("", None, "••••••"):
                continue  # ไม่แก้ค่า secret ถ้าผู้ใช้ไม่ได้กรอกใหม่
            clean[k] = coerce(d, v)
        changed = {k: v for k, v in clean.items() if self.get(k) != v}
        if not changed:
            return {}
        with self.db.session() as s:
            for k, v in changed.items():
                row = s.get(Setting, k)
                if row is None:
                    s.add(Setting(key=k, value=json.dumps(v, ensure_ascii=False)))
                else:
                    row.value = json.dumps(v, ensure_ascii=False)
        with self._lock:
            self._cache.update(changed)
        for fn in self._listeners:
            try:
                fn(changed)
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).exception("settings listener failed")
        return changed

    def schema(self) -> list[dict[str, Any]]:
        out = []
        for d in DEFS:
            item = asdict(d)
            item["options"] = list(d.options)
            v = self.get(d.key)
            if d.secret:
                item["value"] = ""
                item["has_value"] = bool(v)
            else:
                item["value"] = v
            out.append(item)
        return out

    def camera_params(self) -> dict[str, Any]:
        """ค่าที่ส่งให้ process กล้อง"""
        return {d.key: self.get(d.key) for d in DEFS if d.cameras}
