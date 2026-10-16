"""รวมทุกส่วนของโปรแกรมไว้ในที่เดียว (ฐานข้อมูล, ค่าตั้งค่า, กล้อง, เหตุการณ์, แจ้งเตือน, งานเบื้องหลัง)"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from .api.auth import LoginLimiter
from .api.hub import Hub
from .camera.manager import CameraManager
from .config import Paths, default_home
from .credentials import CredentialStore
from .db.session import Database
from .events.service import EventService
from .maintenance import Maintenance
from .notify import Notifier, ensure_vapid
from .settings import DEF_BY_KEY, SettingsStore

log = logging.getLogger(__name__)


class AppContext:
    def __init__(self, home: Path | None = None, start_cameras: bool = True) -> None:
        self.paths = Paths(home or default_home()).ensure()
        self.db = Database(self.paths.db)
        self.settings = SettingsStore(self.db)
        self.hub = Hub()
        self.creds = CredentialStore(self.paths.data)
        self.notifier = Notifier(self.db, self.settings)
        self.events = EventService(self.db, self.settings, self.paths, publish=self.hub.publish, notify=self.notifier)
        self.cameras = CameraManager(self.db, self.settings, self.paths, self.creds,
                                     on_event=self.events.ingest, on_clip=self.events.attach_clip,
                                     publish=self.hub.publish, on_revise=self.events.revise)
        self.maintenance = Maintenance(self.db, self.settings, self.paths, self.events, self.notifier,
                                       self.hub.publish)
        self.limiter = LoginLimiter()
        self.start_cameras = start_cameras
        self.restart_required: set[str] = set()
        self.settings.on_change(self._on_settings)
        try:
            ensure_vapid(self.settings)
        except Exception:  # noqa: BLE001
            log.exception("สร้างกุญแจ VAPID ไม่สำเร็จ")

    def start(self) -> None:
        self.maintenance.start()
        if self.start_cameras:
            threading.Thread(target=self.cameras.start_all, daemon=True, name="cam-start").start()

    def stop(self) -> None:
        self.maintenance.stop()
        self.cameras.shutdown()

    def _on_settings(self, changed: dict[str, Any]) -> None:
        keys = [k for k in changed if k in DEF_BY_KEY]
        if any(DEF_BY_KEY[k].cameras for k in keys) and self.start_cameras:
            threading.Thread(target=self.cameras.restart_all, daemon=True, name="cam-reload").start()
        for k in keys:
            if DEF_BY_KEY[k].restart:
                self.restart_required.add(k)
