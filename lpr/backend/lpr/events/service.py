"""รับเหตุการณ์จากกล้อง -> กันบันทึกซ้ำ -> ตั้งสถานะตรวจสอบ -> ผูกกับรถ -> จับคู่เข้า-ออก -> บันทึกภาพ
-> แจ้งเตือน -> ส่งขึ้นหน้าจอแบบสด"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from .. import constants as C
from ..config import Paths
from ..db.models import AuditLog, Camera, Event, Vehicle, Visit
from ..db.session import Database
from ..plates.parser import format_display, normalize_plate_text
from ..plates.provinces import match_province
from ..settings import SettingsStore
from . import visits as V

log = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Bangkok")


def color_code(bg: str, fg: str) -> str:
    return f"{bg or 'unknown'}/{fg or 'unknown'}"


def _alts(raw: str) -> list[dict[str, Any]]:
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def audit(s: Session, user: str, action: str, detail: str = "") -> None:
    s.add(AuditLog(ts=time.time(), user=user or "system", action=action, detail=detail[:4000]))


class EventService:
    def __init__(self, db: Database, settings: SettingsStore, paths: Paths,
                 publish: Callable[[dict[str, Any]], None] | None = None,
                 notify: Callable[..., None] | None = None) -> None:
        self.db = db
        self.settings = settings
        self.paths = paths
        self.publish = publish or (lambda m: None)
        self.notify = notify or (lambda **kw: None)
        self._lock = threading.Lock()
        self._pending_clips: dict[str, str] = {}  # clip มาถึงก่อนเหตุการณ์ถูกบันทึก

    # ------------------------------------------------------------------ files
    def _day_dir(self, ts: float) -> tuple[Path, str]:
        d = datetime.fromtimestamp(ts, TZ)
        rel = f"images/{d:%Y}/{d:%m}/{d:%d}"
        p = self.paths.data / rel
        p.mkdir(parents=True, exist_ok=True)
        return p, rel

    def _save_images(self, ev: Event, full: bytes, plate: bytes) -> None:
        p, rel = self._day_dir(ev.ts)
        if full:
            (p / f"{ev.id}_full.jpg").write_bytes(full)
            ev.image_full_path = f"{rel}/{ev.id}_full.jpg"
            img = cv2.imdecode(np.frombuffer(full, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                tw = 360
                th = cv2.resize(img, (tw, int(h * tw / w)), interpolation=cv2.INTER_AREA)
                ok, b = cv2.imencode(".jpg", th, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    (p / f"{ev.id}_thumb.jpg").write_bytes(b.tobytes())
                    ev.image_thumb_path = f"{rel}/{ev.id}_thumb.jpg"
        if plate:
            (p / f"{ev.id}_plate.jpg").write_bytes(plate)
            ev.image_plate_path = f"{rel}/{ev.id}_plate.jpg"

    def abs_path(self, rel: str) -> Path | None:
        if not rel:
            return None
        p = (self.paths.data / rel).resolve()
        try:
            p.relative_to(self.paths.data.resolve())
        except ValueError:
            return None
        return p if p.exists() else None

    # ------------------------------------------------------------------ vehicles
    def find_or_create_vehicle(self, s: Session, norm: str, province: str, vtype: str, ts: float) -> Vehicle:
        province = province or ""
        v = s.scalar(select(Vehicle).where(Vehicle.plate_norm == norm, Vehicle.province == province))
        if v is None and province:
            # เคยพบโดยไม่รู้จังหวัด -> เติมจังหวัดให้
            v = s.scalar(select(Vehicle).where(Vehicle.plate_norm == norm, Vehicle.province == ""))
            if v is not None:
                v.province = province
        if v is None and not province:
            same = s.scalars(select(Vehicle).where(Vehicle.plate_norm == norm)).all()
            if len(same) == 1:
                v = same[0]
        if v is None:
            v = Vehicle(plate_norm=norm, province=province, vehicle_type=vtype, status=C.VS_UNKNOWN,
                        first_seen=ts, last_seen=ts)
            s.add(v)
            s.flush()
        else:
            v.first_seen = min(v.first_seen or ts, ts)
            v.last_seen = max(v.last_seen or ts, ts)
            if not v.type_locked and vtype and vtype != C.VT_OTHER:
                # ประเภทรถ = ผลส่วนใหญ่จาก 20 ครั้งล่าสุด (กันผลตรวจจับที่แกว่งในบางเฟรม)
                recent = [t for (t,) in s.execute(select(Event.vehicle_type).where(
                    Event.vehicle_id == v.id, Event.vehicle_type != C.VT_OTHER).order_by(Event.ts.desc()).limit(19))]
                recent.append(vtype)
                v.vehicle_type = max(set(recent), key=recent.count)
        return v

    # ------------------------------------------------------------------ visits
    def _apply_visit(self, s: Session, vehicle_id: int, ev: Event) -> None:
        last = s.scalar(select(Visit).where(Visit.vehicle_id == vehicle_id)
                        .order_by(func.coalesce(Visit.exit_ts, Visit.entry_ts).desc(), Visit.id.desc()).limit(1))
        if last is not None and (max(last.entry_ts or 0, last.exit_ts or 0) > ev.ts):
            self.rebuild_visits(s, vehicle_id)  # เหตุการณ์มาไม่เรียงเวลา
            return
        rec = None
        if last is not None:
            rec = V.VisitRec(last.entry_event_id, last.exit_event_id, last.entry_ts, last.exit_ts, last.status, last.id)
        upd, new = V.step(rec, ev.id, ev.ts, ev.direction)
        if upd is not None and last is not None:
            last.exit_event_id, last.exit_ts, last.status = upd.exit_event_id, upd.exit_ts, upd.status
            last.duration_sec = upd.duration_sec
        if new is not None:
            s.add(Visit(vehicle_id=vehicle_id, entry_event_id=new.entry_event_id, exit_event_id=new.exit_event_id,
                        entry_ts=new.entry_ts, exit_ts=new.exit_ts, status=new.status, duration_sec=new.duration_sec))

    def rebuild_visits(self, s: Session, vehicle_id: int) -> None:
        rows = s.execute(select(Event.id, Event.ts, Event.direction).where(Event.vehicle_id == vehicle_id)).all()
        alerted = {v.entry_event_id for v in s.scalars(select(Visit).where(Visit.vehicle_id == vehicle_id,
                                                                            Visit.alerted.is_(True)))}
        s.execute(delete(Visit).where(Visit.vehicle_id == vehicle_id))
        overstay = float(self.settings.get("overstay_hours")) * 3600
        for r in V.rebuild([(a, b, c) for a, b, c in rows], time.time(), overstay):
            s.add(Visit(vehicle_id=vehicle_id, entry_event_id=r.entry_event_id, exit_event_id=r.exit_event_id,
                        entry_ts=r.entry_ts, exit_ts=r.exit_ts, status=r.status, duration_sec=r.duration_sec,
                        alerted=r.entry_event_id in alerted))

    # ------------------------------------------------------------------ ingest
    def review_status_for(self, norm: str, valid: bool, conf: float, province: str, bg: str) -> str:
        if not norm:
            return C.REVIEW_UNREAD
        if not valid or bg == "red" or conf < float(self.settings.get("review_threshold")):
            return C.REVIEW_PENDING
        if not province and self.settings.get("review_if_no_province"):
            return C.REVIEW_PENDING
        return C.REVIEW_OK

    def ingest(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """บันทึกเหตุการณ์จากกล้อง คืน dict ของเหตุการณ์ (หรือ None ถ้าเป็นการบันทึกซ้ำ)"""
        with self._lock:
            return self._ingest(msg)

    def _ingest(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        ts = float(msg.get("ts") or time.time())
        cam_id = msg.get("camera_id")
        norm = msg.get("plate_norm") or ""
        province = msg.get("province") or ""
        source = msg.get("source", C.SOURCE_AUTO)
        with self.db.session() as s:
            # กันบันทึกซ้ำ: ป้ายเดียวกัน กล้องเดียวกัน ภายในเวลาที่ตั้ง
            if source == C.SOURCE_AUTO:
                window = float(self.settings.get("dedup_seconds" if norm else "dedup_unread_seconds"))
                if window > 0:
                    cond = [Event.camera_id == cam_id, Event.ts >= ts - window, Event.ts <= ts + 1]
                    cond.append(Event.plate_norm == norm if norm else Event.review_status == C.REVIEW_UNREAD)
                    dup = s.scalar(select(Event).where(and_(*cond)).order_by(Event.ts.desc()).limit(1))
                    if dup is not None:
                        log.info("ข้ามการบันทึกซ้ำ %s กล้อง %s", norm or "(อ่านไม่ได้)", cam_id)
                        if dup.vehicle_id:
                            v = s.get(Vehicle, dup.vehicle_id)
                            if v is not None:
                                v.last_seen = max(v.last_seen or ts, ts)
                        self._pending_clips.pop(msg.get("uid", ""), None)
                        return None
            review = self.review_status_for(norm, bool(msg.get("valid")), float(msg.get("confidence") or 0),
                                            province, msg.get("plate_bg", ""))
            vtype = msg.get("vehicle_type") or C.VT_OTHER
            ev = Event(uid=msg.get("uid") or uuid.uuid4().hex, ts=ts, camera_id=cam_id,
                       direction=msg.get("direction") or C.DIR_IN, plate_raw=msg.get("plate_raw", ""),
                       plate_norm=norm, province=province, ocr_confidence=float(msg.get("confidence") or 0),
                       vehicle_type=vtype, plate_color=color_code(msg.get("plate_bg", ""), msg.get("plate_fg", "")),
                       review_status=review, source=source, yolo_class=msg.get("yolo_class", ""),
                       frames_used=int(msg.get("frames") or 0), night=bool(msg.get("night")),
                       note=msg.get("note", ""), edited_by=msg.get("edited_by", ""),
                       alternatives=json.dumps(msg.get("alternatives") or [], ensure_ascii=False),
                       edited_at=time.time() if msg.get("edited_by") else None)
            vehicle = None
            if norm:
                vehicle = self.find_or_create_vehicle(s, norm, province, vtype, ts)
                ev.vehicle_id = vehicle.id
                if vehicle.type_locked and vehicle.vehicle_type:
                    ev.vehicle_type = vehicle.vehicle_type
            s.add(ev)
            s.flush()
            self._save_images(ev, msg.get("full_jpg") or b"", msg.get("plate_jpg") or b"")
            clip = self._pending_clips.pop(ev.uid, None)
            if clip:
                self._move_clip(ev, clip)
            if vehicle is not None:
                self._apply_visit(s, vehicle.id, ev)
            out = self.event_dict(s, ev)
        self.publish({"type": "event", "event": out})
        self._maybe_alert(out)
        return out

    def revise(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """กล้องอ่านป้ายได้ดีขึ้นหลังบันทึกไปแล้ว: ปรับผลของเหตุการณ์เดิม (ถ้าผู้ใช้ยังไม่ได้แก้เอง)"""
        with self._lock, self.db.session() as s:
            ev = s.scalar(select(Event).where(Event.uid == msg.get("uid")))
            if ev is None or ev.edited_by or ev.review_status == C.REVIEW_EDITED:
                return None
            old_vehicle = ev.vehicle_id
            norm, province = msg.get("plate_norm") or "", msg.get("province") or ""
            ev.plate_norm, ev.province = norm, province
            ev.plate_raw = msg.get("plate_raw", ev.plate_raw)
            ev.ocr_confidence = float(msg.get("confidence") or 0)
            ev.frames_used = int(msg.get("frames") or ev.frames_used)
            ev.alternatives = json.dumps(msg.get("alternatives") or [], ensure_ascii=False)
            ev.plate_color = color_code(msg.get("plate_bg", ""), msg.get("plate_fg", ""))
            ev.review_status = self.review_status_for(norm, bool(msg.get("valid")), ev.ocr_confidence, province,
                                                      msg.get("plate_bg", ""))
            if msg.get("vehicle_type"):
                ev.vehicle_type = msg["vehicle_type"]
            ev.vehicle_id = None
            if norm:
                v = self.find_or_create_vehicle(s, norm, province, ev.vehicle_type, ev.ts)
                ev.vehicle_id = v.id
                if v.type_locked and v.vehicle_type:
                    ev.vehicle_type = v.vehicle_type
            if msg.get("full_jpg") or msg.get("plate_jpg"):
                self._save_images(ev, msg.get("full_jpg") or b"", msg.get("plate_jpg") or b"")
            s.flush()
            for vid in {old_vehicle, ev.vehicle_id} - {None}:
                self.rebuild_visits(s, vid)  # type: ignore[arg-type]
            out = self.event_dict(s, ev)
        self.publish({"type": "event_update", "event": out})
        return out

    def _move_clip(self, ev: Event, src: str) -> None:
        sp = Path(src)
        if not sp.exists():
            return
        p, rel = self._day_dir(ev.ts)
        dst = p / f"{ev.id}_clip{sp.suffix}"
        shutil.move(str(sp), dst)
        ev.clip_path = f"{rel}/{dst.name}"

    def attach_clip(self, uid: str, path: str) -> None:
        with self._lock, self.db.session() as s:
            ev = s.scalar(select(Event).where(Event.uid == uid))
            if ev is None:
                self._pending_clips[uid] = path
                # ถ้าเป็นเหตุการณ์ซ้ำที่ถูกข้าม ไฟล์จะถูกลบตอนตรวจ tmp รอบถัดไป
                return
            self._move_clip(ev, path)
            out = self.event_dict(s, ev)
        self.publish({"type": "event_update", "event": out})

    def _maybe_alert(self, e: dict[str, Any]) -> None:
        st = self.settings
        status = e.get("vehicle_status")
        kind = None
        if status == C.VS_WATCH and st.get("notify_watch"):
            kind = "watch"
        elif status == C.VS_UNKNOWN and st.get("notify_unknown"):
            kind = "unknown"
        elif not e.get("plate_norm") and st.get("notify_unread"):
            kind = "unread"
        if kind is None:
            return
        title = {"watch": "⚠️ พบรถเฝ้าระวัง", "unknown": "พบรถไม่รู้จัก", "unread": "อ่านป้ายไม่ได้"}[kind]
        when = datetime.fromtimestamp(e["ts"], TZ).strftime("%H:%M:%S")
        body = f"{e.get('plate_display') or '-'} {e.get('province') or ''} · {e['direction']} · {when} · {e.get('camera_name') or ''}"
        img = self.abs_path(e.get("_thumb_rel", "")) or self.abs_path(e.get("_full_rel", ""))
        try:
            self.notify(title=title, body=body.strip(), image=img, url=f"/?event={e['id']}", tag=f"event-{e['id']}",
                        kind=kind)
        except Exception:  # noqa: BLE001
            log.exception("notify failed")

    # ------------------------------------------------------------------ serialize
    def event_dict(self, s: Session, ev: Event, cams: dict[int, str] | None = None,
                   vehicles: dict[int, Vehicle] | None = None) -> dict[str, Any]:
        cam_name = ""
        if ev.camera_id is not None:
            if cams is not None:
                cam_name = cams.get(ev.camera_id, "")
            else:
                c = s.get(Camera, ev.camera_id)
                cam_name = c.name if c else ""
        v = None
        if ev.vehicle_id is not None:
            v = vehicles.get(ev.vehicle_id) if vehicles is not None else s.get(Vehicle, ev.vehicle_id)
        bg, _, fg = (ev.plate_color or "unknown/unknown").partition("/")
        return {
            "id": ev.id, "uid": ev.uid, "ts": ev.ts, "camera_id": ev.camera_id, "camera_name": cam_name,
            "direction": ev.direction, "plate_raw": ev.plate_raw, "plate_norm": ev.plate_norm,
            "plate_display": format_display(ev.plate_norm) if ev.plate_norm else "", "province": ev.province,
            "ocr_confidence": round(ev.ocr_confidence or 0, 3), "vehicle_type": ev.vehicle_type,
            "plate_bg": bg, "plate_fg": fg, "vehicle_id": ev.vehicle_id,
            "vehicle_status": v.status if v else None, "owner_name": v.owner_name if v else "",
            "house_no": v.house_no if v else "", "review_status": ev.review_status,
            "has_full": bool(ev.image_full_path), "has_plate": bool(ev.image_plate_path),
            "has_thumb": bool(ev.image_thumb_path), "has_clip": bool(ev.clip_path),
            "clip_ext": Path(ev.clip_path).suffix.lstrip(".") if ev.clip_path else "",
            "source": ev.source, "original_plate": ev.original_plate, "edited_by": ev.edited_by,
            "edited_at": ev.edited_at, "night": ev.night, "frames_used": ev.frames_used, "note": ev.note,
            "alternatives": _alts(ev.alternatives),
            "_thumb_rel": ev.image_thumb_path, "_full_rel": ev.image_full_path,
        }

    # ------------------------------------------------------------------ edit
    def edit_event(self, event_id: int, changes: dict[str, Any], user: str) -> dict[str, Any]:
        with self._lock, self.db.session() as s:
            ev = s.get(Event, event_id)
            if ev is None:
                raise KeyError("ไม่พบเหตุการณ์")
            old_vehicle = ev.vehicle_id
            detail = []
            plate_changed = False
            if "plate" in changes or "province" in changes:
                new_norm = ev.plate_norm
                if "plate" in changes:
                    n, _, _ = normalize_plate_text(str(changes["plate"] or ""))
                    new_norm = n
                new_prov = ev.province
                if "province" in changes:
                    pv = str(changes["province"] or "").strip()
                    new_prov = (match_province(pv, 70)[0] or pv) if pv else ""
                if (new_norm, new_prov) != (ev.plate_norm, ev.province):
                    if not ev.original_plate:
                        ev.original_plate = f"{format_display(ev.plate_norm) or '-'} {ev.province}".strip()
                    detail.append(f"ทะเบียน {format_display(ev.plate_norm) or '-'} {ev.province} -> "
                                  f"{format_display(new_norm) or '-'} {new_prov}")
                    ev.plate_norm, ev.province = new_norm, new_prov
                    plate_changed = True
            for f in ("vehicle_type", "direction", "note"):
                if f in changes and changes[f] is not None and changes[f] != getattr(ev, f):
                    if f == "direction" and changes[f] not in C.DIRECTIONS:
                        raise ValueError("ทิศทางไม่ถูกต้อง")
                    if f == "vehicle_type" and changes[f] not in C.VEHICLE_TYPES:
                        raise ValueError("ประเภทรถไม่ถูกต้อง")
                    detail.append(f"{f}: {getattr(ev, f)} -> {changes[f]}")
                    setattr(ev, f, changes[f])
            if plate_changed:
                if ev.plate_norm:
                    v = self.find_or_create_vehicle(s, ev.plate_norm, ev.province, ev.vehicle_type, ev.ts)
                    ev.vehicle_id = v.id
                else:
                    ev.vehicle_id = None
            if "review_status" in changes and changes["review_status"] in C.REVIEW_STATUSES:
                ev.review_status = changes["review_status"]
            elif detail:
                ev.review_status = C.REVIEW_EDITED if ev.plate_norm else C.REVIEW_UNREAD
            ev.edited_by, ev.edited_at = user, time.time()
            s.flush()
            for vid in {old_vehicle, ev.vehicle_id} - {None}:
                self.rebuild_visits(s, vid)  # type: ignore[arg-type]
            audit(s, user, "แก้ไขเหตุการณ์", f"#{ev.id}: " + "; ".join(detail or ["ยืนยันผล"]))
            out = self.event_dict(s, ev)
        self.publish({"type": "event_update", "event": out})
        return out

    def delete_event(self, event_id: int, user: str) -> None:
        with self._lock, self.db.session() as s:
            ev = s.get(Event, event_id)
            if ev is None:
                raise KeyError("ไม่พบเหตุการณ์")
            for rel in (ev.image_full_path, ev.image_plate_path, ev.image_thumb_path, ev.clip_path):
                p = self.abs_path(rel)
                if p:
                    p.unlink(missing_ok=True)
            vid = ev.vehicle_id
            s.execute(delete(Visit).where(or_(Visit.entry_event_id == ev.id, Visit.exit_event_id == ev.id)))
            audit(s, user, "ลบเหตุการณ์", f"#{ev.id} {format_display(ev.plate_norm)} {ev.province}")
            s.delete(ev)
            s.flush()
            if vid:
                self.rebuild_visits(s, vid)
        self.publish({"type": "event_delete", "id": event_id})

    def manual_event(self, data: dict[str, Any], user: str, full_jpg: bytes = b"") -> dict[str, Any]:
        """บันทึกด้วยมือ"""
        norm, kind, valid = normalize_plate_text(str(data.get("plate") or ""))
        pv = str(data.get("province") or "").strip()
        province = (match_province(pv, 70)[0] or pv) if pv else ""
        direction = data.get("direction") or C.DIR_IN
        if direction not in C.DIRECTIONS:
            raise ValueError("ทิศทางไม่ถูกต้อง")
        msg = {"uid": uuid.uuid4().hex, "ts": float(data.get("ts") or time.time()),
               "camera_id": data.get("camera_id"), "direction": direction, "plate_norm": norm,
               "plate_raw": str(data.get("plate") or ""), "province": province, "confidence": 1.0, "valid": True,
               "vehicle_type": data.get("vehicle_type") or C.VT_OTHER, "source": C.SOURCE_MANUAL,
               "note": data.get("note", ""), "edited_by": user, "full_jpg": full_jpg}
        out = self.ingest(msg)
        assert out is not None
        with self.db.session() as s:
            ev = s.get(Event, out["id"])
            if ev is not None:
                ev.review_status = C.REVIEW_OK if norm else C.REVIEW_UNREAD
                audit(s, user, "บันทึกด้วยมือ", f"#{ev.id} {format_display(norm)} {province} {direction}")
                out = self.event_dict(s, ev)
        self.publish({"type": "event_update", "event": out})
        return out

    # ------------------------------------------------------------------ periodic
    def check_overstay(self) -> list[dict[str, Any]]:
        """ติดสถานะ ไม่พบการออก และแจ้งเตือนรถที่อยู่นานเกินเวลา"""
        now = time.time()
        overstay = float(self.settings.get("overstay_hours")) * 3600
        alert_after = float(self.settings.get("long_stay_alert_hours")) * 3600
        alerts = []
        with self._lock, self.db.session() as s:
            for v in s.scalars(select(Visit).where(Visit.status == C.VISIT_INSIDE, Visit.entry_ts < now - overstay)):
                v.status = C.VISIT_NO_EXIT
            if self.settings.get("notify_overstay"):
                q = (select(Visit, Vehicle).join(Vehicle, Vehicle.id == Visit.vehicle_id)
                     .where(Visit.status == C.VISIT_INSIDE, Visit.alerted.is_(False),
                            Visit.entry_ts < now - alert_after,
                            Vehicle.status.in_([C.VS_UNKNOWN, C.VS_WATCH])))
                for visit, veh in s.execute(q).all():
                    visit.alerted = True
                    alerts.append({"plate": f"{format_display(veh.plate_norm)} {veh.province}".strip(),
                                   "hours": (now - (visit.entry_ts or now)) / 3600, "vehicle_id": veh.id})
        for a in alerts:
            try:
                self.notify(title="รถอยู่นานเกินเวลาที่ตั้ง", body=f"{a['plate']} อยู่ในพื้นที่ {a['hours']:.1f} ชั่วโมง",
                            image=None, url=f"/vehicles/{a['vehicle_id']}", tag=f"stay-{a['vehicle_id']}",
                            kind="overstay")
            except Exception:  # noqa: BLE001
                log.exception("notify failed")
        return alerts

    def cleanup_tmp(self, max_age: float = 3600) -> None:
        now = time.time()
        for p in self.paths.tmp.glob("*"):
            try:
                if p.is_file() and now - p.stat().st_mtime > max_age:
                    p.unlink()
            except OSError:
                pass
