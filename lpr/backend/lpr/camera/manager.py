"""จัดการ process กล้องทั้งหมด: เริ่ม/หยุด, รับเหตุการณ์, ภาพสด, และ watchdog รีสตาร์ต process ที่ค้างหรือหลุด"""
from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select

from ..config import Paths, find_model
from ..credentials import CredentialStore
from ..db.models import Camera
from ..db.session import Database
from ..settings import SettingsStore
from ..vision.runtime import default_threads
from .worker import camera_dict, worker_main

log = logging.getLogger(__name__)

STATE_TH = {"starting": "กำลังเริ่ม", "online": "ออนไลน์", "connecting": "กำลังเชื่อมต่อ", "error": "ผิดพลาด",
            "stopped": "ปิดใช้งาน", "restarting": "กำลังรีสตาร์ต"}


@dataclass
class Handle:
    cam: dict[str, Any]
    proc: Any
    cmd_q: Any
    out_q: Any
    preview_q: Any
    started: float
    status: dict[str, Any] = field(default_factory=dict)
    last_heartbeat: float = 0.0
    preview: tuple[float, bytes] | None = None
    restarts: int = 0
    info: dict[str, Any] = field(default_factory=dict)
    stopping: bool = False


class CameraManager:
    def __init__(self, db: Database, settings: SettingsStore, paths: Paths, creds: CredentialStore,
                 on_event: Callable[[dict[str, Any]], Any], on_clip: Callable[[str, str], Any],
                 publish: Callable[[dict[str, Any]], None],
                 on_revise: Callable[[dict[str, Any]], Any] | None = None) -> None:
        self.db, self.settings, self.paths, self.creds = db, settings, paths, creds
        self.on_event, self.on_clip, self.publish = on_event, on_clip, publish
        self.on_revise = on_revise or (lambda m: None)
        self.ctx = mp.get_context("spawn")
        self.log_q = self.ctx.Queue(2000)
        self.handles: dict[int, Handle] = {}
        self._lock = threading.RLock()
        self._waiters: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        self._stop = threading.Event()
        self._io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="event-db")
        threading.Thread(target=self._log_pump, daemon=True, name="cam-log").start()
        threading.Thread(target=self._watchdog, daemon=True, name="cam-watchdog").start()

    # ------------------------------------------------------------------ lifecycle
    def model_paths(self) -> dict[str, str | None]:
        out = {}
        for k in ("vehicle", "plate", "ocr_rec", "ocr_dict", "ocr_det"):
            p = find_model(self.paths, k)
            out[k] = str(p) if p else None
        return out

    def start_all(self) -> None:
        with self.db.session() as s:
            cams = s.scalars(select(Camera).where(Camera.enabled.is_(True)).order_by(Camera.sort_order, Camera.id)).all()
        for c in cams:
            self.start(c.id)

    def _cam_row(self, cam_id: int) -> Camera | None:
        with self.db.session() as s:
            return s.get(Camera, cam_id)

    def start(self, cam_id: int) -> None:
        row = self._cam_row(cam_id)
        if row is None or not row.enabled:
            return
        with self._lock:
            old = self.handles.get(cam_id)
            if old is not None and old.proc.is_alive():
                return
            cam = camera_dict(row, self.creds.get(cam_id) if row.username else "")
            n = max(1, sum(1 for h in self.handles.values() if h.proc.is_alive()) + 1)
            cmd_q, out_q, prev_q = self.ctx.Queue(50), self.ctx.Queue(500), self.ctx.Queue(2)
            dirs = {"tmp": str(self.paths.tmp), "collect": str(self.paths.plate_collect)}
            proc = self.ctx.Process(target=worker_main, name=f"lpr-cam-{cam_id}",
                                    args=(cam, self.settings.camera_params(), self.model_paths(), dirs,
                                          default_threads(n), cmd_q, out_q, prev_q, self.log_q), daemon=True)
            proc.start()
            h = Handle(cam, proc, cmd_q, out_q, prev_q, time.time(),
                       status={"state": "starting"}, restarts=old.restarts if old else 0)
            self.handles[cam_id] = h
            threading.Thread(target=self._pump, args=(cam_id, h), daemon=True, name=f"cam-pump-{cam_id}").start()
            log.info("เริ่มกล้อง %s (%s)", cam_id, row.name)

    def stop(self, cam_id: int) -> None:
        with self._lock:
            h = self.handles.pop(cam_id, None)
        if h is None:
            return
        h.stopping = True
        try:
            h.cmd_q.put_nowait({"cmd": "stop"})
        except Exception:  # noqa: BLE001
            pass
        h.proc.join(timeout=5)
        if h.proc.is_alive():
            h.proc.terminate()
            h.proc.join(timeout=3)
        log.info("หยุดกล้อง %s", cam_id)

    def restart(self, cam_id: int) -> None:
        restarts = self.handles[cam_id].restarts if cam_id in self.handles else 0
        self.stop(cam_id)
        self.start(cam_id)
        if cam_id in self.handles:
            self.handles[cam_id].restarts = restarts

    def restart_all(self) -> None:
        for cid in list(self.handles):
            self.stop(cid)
        self.start_all()

    def shutdown(self) -> None:
        self._stop.set()
        for cid in list(self.handles):
            self.stop(cid)
        self._io.shutdown(wait=True)

    # ------------------------------------------------------------------ messages
    def _pump(self, cam_id: int, h: Handle) -> None:
        while not self._stop.is_set() and not h.stopping:
            try:
                msg = h.out_q.get(timeout=0.5)
            except queue.Empty:
                self._drain_preview(h)
                if not h.proc.is_alive():
                    break
                continue
            except (EOFError, OSError):
                break
            self._drain_preview(h)
            t = msg.get("type")
            if t == "status":
                h.last_heartbeat = time.time()
                h.status = msg
                self.publish({"type": "camera_status", "camera_id": cam_id, "status": self.status_of(cam_id)})
            elif t == "info":
                h.info = {k: v for k, v in msg.items() if k not in ("type", "camera_id")}
                h.last_heartbeat = time.time()
            elif t == "event":
                self._io.submit(self._safe, self.on_event, msg)
            elif t == "event_revise":
                self._io.submit(self._safe, self.on_revise, msg)
            elif t == "clip":
                self._io.submit(self._safe, self.on_clip, msg["uid"], msg["path"])
            elif t in ("snapshot", "capture_done"):
                w = self._waiters.get(msg.get("req", ""))
                if w:
                    w[1].update(msg)
                    w[0].set()

    def _drain_preview(self, h: Handle) -> None:
        try:
            while True:
                h.preview = h.preview_q.get_nowait()
        except (queue.Empty, EOFError, OSError):
            pass

    @staticmethod
    def _safe(fn: Callable, *a: Any) -> None:  # type: ignore[type-arg]
        try:
            fn(*a)
        except Exception:  # noqa: BLE001
            log.exception("handler failed")

    def _log_pump(self) -> None:
        while not self._stop.is_set():
            try:
                rec = self.log_q.get(timeout=1)
            except queue.Empty:
                continue
            except (EOFError, OSError):
                return
            try:
                logging.getLogger(rec.name).handle(rec)
            except Exception:  # noqa: BLE001
                pass

    def _watchdog(self) -> None:
        while not self._stop.wait(5):
            now = time.time()
            for cid, h in list(self.handles.items()):
                if h.stopping:
                    continue
                dead = not h.proc.is_alive()
                grace = 90 if not h.last_heartbeat else 30  # ช่วงแรกรอโหลดโมเดล
                hung = now - max(h.last_heartbeat, h.started) > grace
                if h.status.get("state") == "error" and not dead:
                    continue
                if dead or hung:
                    wait = min(300, 5 * (2 ** min(h.restarts, 6)))
                    if now - h.started < wait:
                        continue
                    log.warning("watchdog: กล้อง %s %s -> รีสตาร์ต (ครั้งที่ %d)", cid, "หยุดทำงาน" if dead else "ค้าง",
                                h.restarts + 1)
                    h.status = {"state": "restarting"}
                    self.publish({"type": "camera_status", "camera_id": cid, "status": self.status_of(cid)})
                    restarts = h.restarts + 1
                    try:
                        self.stop(cid)
                        self.start(cid)
                        if cid in self.handles:
                            self.handles[cid].restarts = restarts
                    except Exception:  # noqa: BLE001
                        log.exception("restart failed")

    # ------------------------------------------------------------------ requests
    def request(self, cam_id: int, cmd: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
        h = self.handles.get(cam_id)
        if h is None or not h.proc.is_alive():
            return {"error": "กล้องไม่ได้ทำงาน"}
        req = uuid.uuid4().hex
        ev = threading.Event()
        res: dict[str, Any] = {}
        self._waiters[req] = (ev, res)
        try:
            h.cmd_q.put({**cmd, "req": req}, timeout=2)
            if not ev.wait(timeout):
                return {"error": "กล้องไม่ตอบสนอง"}
            return res
        finally:
            self._waiters.pop(req, None)

    def want_preview(self, cam_id: int) -> None:
        h = self.handles.get(cam_id)
        if h is not None:
            try:
                h.cmd_q.put_nowait({"cmd": "preview", "on": True})
            except Exception:  # noqa: BLE001
                pass

    def latest_preview(self, cam_id: int) -> tuple[float, bytes] | None:
        h = self.handles.get(cam_id)
        if h is None:
            return None
        self._drain_preview(h)
        return h.preview

    def status_of(self, cam_id: int) -> dict[str, Any]:
        h = self.handles.get(cam_id)
        if h is None:
            return {"state": "stopped", "state_th": STATE_TH["stopped"]}
        st = {k: v for k, v in h.status.items() if k not in ("type",)}
        state = st.get("state", "starting")
        if not h.proc.is_alive() and not h.stopping and state != "error":
            state = "restarting"
        if h.last_heartbeat and time.time() - h.last_heartbeat > 15 and state == "online":
            state = "connecting"
        st.update(state=state, state_th=STATE_TH.get(state, state), restarts=h.restarts, **h.info)
        return st

    def all_status(self) -> dict[int, dict[str, Any]]:
        return {cid: self.status_of(cid) for cid in list(self.handles)}
