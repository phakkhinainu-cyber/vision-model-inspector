"""งานเบื้องหลังตามเวลา: สำรองฐานข้อมูลทุกวัน, ลบภาพ/ข้อมูลเก่า, เตือนพื้นที่ดิสก์, ตรวจรถอยู่เกินเวลา"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import delete, or_, select, update

from .config import Paths
from .db.models import AuditLog, Event, SessionRow, Vehicle, Visit
from .db.session import Database
from .events.service import EventService
from .settings import SettingsStore

log = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Bangkok")


def disk_usage(path: Path) -> dict[str, Any]:
    p = path
    while not p.exists() and p.parent != p:
        p = p.parent
    u = shutil.disk_usage(p)
    return {"path": str(path), "total": u.total, "free": u.free, "used": u.used,
            "free_percent": round(100 * u.free / u.total, 1) if u.total else 0}


class Maintenance:
    def __init__(self, db: Database, settings: SettingsStore, paths: Paths, events: EventService,
                 notify: Callable[..., None], publish: Callable[[dict[str, Any]], None]) -> None:
        self.db, self.settings, self.paths, self.events = db, settings, paths, events
        self.notify, self.publish = notify, publish
        self._stop = threading.Event()
        self._last_backup_day = ""
        self._last_cleanup_day = ""
        self._last_disk_alert = 0.0
        self.alerts: dict[str, str] = {}
        self.last_backup: dict[str, Any] = {}

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="maintenance").start()

    def stop(self) -> None:
        self._stop.set()

    def backup_dir(self) -> Path:
        d = str(self.settings.get("backup_dir") or "").strip()
        return Path(d) if d else self.paths.backup_default

    # ---------------------------------------------------------------- jobs
    def run_backup(self, user: str = "system") -> dict[str, Any]:
        d = self.backup_dir()
        d.mkdir(parents=True, exist_ok=True)
        name = datetime.now(TZ).strftime("lpr-%Y%m%d-%H%M%S.db")
        dst = d / name
        self.db.backup_to(dst)
        keep = int(self.settings.get("backup_keep"))
        files = sorted(d.glob("lpr-*.db"))
        for old in files[:-keep]:
            old.unlink(missing_ok=True)
        self.last_backup = {"file": str(dst), "ts": time.time(), "size": dst.stat().st_size}
        with self.db.session() as s:
            s.add(AuditLog(ts=time.time(), user=user, action="สำรองข้อมูล", detail=str(dst)))
        log.info("สำรองฐานข้อมูลไปที่ %s", dst)
        return self.last_backup

    def list_backups(self) -> list[dict[str, Any]]:
        d = self.backup_dir()
        if not d.exists():
            return []
        return [{"file": p.name, "size": p.stat().st_size, "ts": p.stat().st_mtime}
                for p in sorted(d.glob("lpr-*.db"), reverse=True)]

    def cleanup(self) -> dict[str, int]:
        now = time.time()
        img_cut = now - int(self.settings.get("image_retention_days")) * 86400
        row_cut = now - int(self.settings.get("row_retention_days")) * 86400
        removed_files = 0
        with self.db.session() as s:
            old = s.scalars(select(Event).where(Event.ts < img_cut, or_(
                Event.image_full_path != "", Event.image_plate_path != "", Event.clip_path != "",
                Event.image_thumb_path != ""))).all()
            for ev in old:
                for rel in (ev.image_full_path, ev.image_plate_path, ev.image_thumb_path, ev.clip_path):
                    p = self.events.abs_path(rel)
                    if p:
                        p.unlink(missing_ok=True)
                        removed_files += 1
                ev.image_full_path = ev.image_plate_path = ev.image_thumb_path = ev.clip_path = ""
            old_ids = [i for (i,) in s.execute(select(Event.id).where(Event.ts < row_cut))]
            if old_ids:
                s.execute(update(Visit).where(Visit.entry_event_id.in_(old_ids)).values(entry_event_id=None))
                s.execute(update(Visit).where(Visit.exit_event_id.in_(old_ids)).values(exit_event_id=None))
                s.execute(delete(Visit).where(Visit.entry_event_id.is_(None), Visit.exit_event_id.is_(None)))
                s.execute(delete(Event).where(Event.id.in_(old_ids)))
            s.execute(delete(Vehicle).where(Vehicle.status == "ไม่รู้จัก", Vehicle.last_seen < row_cut,
                                            Vehicle.owner_name == "", Vehicle.note == ""))
            s.execute(delete(AuditLog).where(AuditLog.ts < row_cut))
            s.execute(delete(SessionRow).where(SessionRow.expires_at < now))
        # ลบโฟลเดอร์วันที่ว่าง
        for d in sorted(self.paths.images.glob("*/*/*"), reverse=True):
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass
        self.events.cleanup_tmp()
        log.info("ลบข้อมูลเก่า: ไฟล์ %d, แถว %d", removed_files, len(old_ids))
        return {"files": removed_files, "rows": len(old_ids)}

    def check_disk(self) -> dict[str, Any]:
        du = disk_usage(self.paths.home)
        warn = float(self.settings.get("disk_warn_percent"))
        if du["free_percent"] < warn:
            msg = f"พื้นที่ดิสก์เหลือ {du['free_percent']}% (ต่ำกว่า {warn:g}%) ที่ {du['path']}"
            if self.alerts.get("disk") != msg:
                self.publish({"type": "alert", "level": "warning", "message": msg})
            self.alerts["disk"] = msg
            if time.time() - self._last_disk_alert > 86400:
                self._last_disk_alert = time.time()
                self.notify(title="พื้นที่ดิสก์ใกล้เต็ม", body=msg, image=None, url="/settings", tag="disk", kind="disk")
        else:
            self.alerts.pop("disk", None)
        return du

    def _loop(self) -> None:
        last_disk = last_overstay = 0.0
        while not self._stop.wait(20):
            now = time.time()
            local = datetime.now(TZ)
            day = local.strftime("%Y-%m-%d")
            hhmm = local.strftime("%H:%M")
            try:
                bt = str(self.settings.get("backup_time"))
                if hhmm >= bt and self._last_backup_day != day:
                    self._last_backup_day = day
                    if not self._backup_done_today(day):
                        self.run_backup()
                if hhmm >= "03:30" and self._last_cleanup_day != day:
                    self._last_cleanup_day = day
                    self.cleanup()
                if now - last_disk > 600:
                    last_disk = now
                    self.check_disk()
                if now - last_overstay > 300:
                    last_overstay = now
                    self.events.check_overstay()
            except Exception:  # noqa: BLE001
                log.exception("maintenance job failed")

    def _backup_done_today(self, day: str) -> bool:
        tag = day.replace("-", "")
        return any(p.name.startswith(f"lpr-{tag}") for p in self.backup_dir().glob("lpr-*.db")) \
            if self.backup_dir().exists() else False
