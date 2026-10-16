"""คำสั่งค้นหาที่ใช้ร่วมกัน: ตัวกรองเหตุการณ์, จำนวนตามหมวด (facets), สถิติรถ"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from .. import constants as C
from ..db.models import Camera, Event, Vehicle, Visit
from ..plates.parser import normalize_query

TZ = ZoneInfo("Asia/Bangkok")


def day_range(date_from: str | None, date_to: str | None) -> tuple[float | None, float | None]:
    """วันที่ (YYYY-MM-DD ปฏิทินสากล ตามเวลาไทย) -> ช่วงเวลา epoch"""
    a = b = None
    if date_from:
        a = datetime.fromisoformat(date_from).replace(tzinfo=TZ).timestamp()
    if date_to:
        b = (datetime.fromisoformat(date_to).replace(tzinfo=TZ) + timedelta(days=1)).timestamp()
    return a, b


def today_range() -> tuple[float, float]:
    d = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return d.timestamp(), (d + timedelta(days=1)).timestamp()


def _csv(v: str | None) -> list[str]:
    return [x for x in (v or "").split(",") if x]


@dataclass
class EventFilter:
    date_from: str | None = None
    date_to: str | None = None
    ts_from: float | None = None
    ts_to: float | None = None
    q: str | None = None
    direction: str | None = None
    types: str | None = None
    vstatus: str | None = None
    cameras: str | None = None
    review: str | None = None
    vehicle_id: int | None = None

    def conditions(self, skip: str = "") -> list[Any]:
        cond: list[Any] = []
        a, b = day_range(self.date_from, self.date_to)
        a = self.ts_from if self.ts_from is not None else a
        b = self.ts_to if self.ts_to is not None else b
        if a is not None:
            cond.append(Event.ts >= a)
        if b is not None:
            cond.append(Event.ts < b)
        if self.q:
            nq = normalize_query(self.q)
            if nq:
                cond.append(or_(Event.plate_norm.contains(nq), Event.province.contains(self.q.strip())))
            else:
                cond.append(Event.province.contains(self.q.strip()))
        if skip != "direction" and self.direction:
            cond.append(Event.direction.in_(_csv(self.direction)))
        if skip != "types" and self.types:
            cond.append(Event.vehicle_type.in_(_csv(self.types)))
        if skip != "cameras" and self.cameras:
            cond.append(Event.camera_id.in_([int(x) for x in _csv(self.cameras)]))
        if self.review:
            cond.append(Event.review_status.in_(_csv(self.review)))
        if self.vehicle_id:
            cond.append(Event.vehicle_id == self.vehicle_id)
        if skip != "vstatus" and self.vstatus:
            st = _csv(self.vstatus)
            c = Vehicle.status.in_(st)
            if C.VS_UNKNOWN in st:
                c = or_(c, Event.vehicle_id.is_(None))
            cond.append(c)
        return cond

    def select(self, *cols: Any, skip: str = "") -> Select:
        q = select(*cols).select_from(Event).outerjoin(Vehicle, Vehicle.id == Event.vehicle_id)
        cond = self.conditions(skip)
        return q.where(and_(*cond)) if cond else q


def list_events(s: Session, f: EventFilter, limit: int, cursor: str | None) -> tuple[list[Event], str | None]:
    q = f.select(Event).order_by(Event.ts.desc(), Event.id.desc())
    if cursor:
        ts_s, id_s = cursor.split("_")
        ts, eid = float(ts_s), int(id_s)
        q = q.where(or_(Event.ts < ts, and_(Event.ts == ts, Event.id < eid)))
    rows = list(s.scalars(q.limit(limit + 1)))
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = f"{rows[-1].ts}_{rows[-1].id}"
    return rows, nxt


def facets(s: Session, f: EventFilter) -> dict[str, Any]:
    def count_by(col: Any, skip: str) -> dict[str, int]:
        q = f.select(col, func.count(Event.id), skip=skip).group_by(col)
        return {str(k) if k is not None else "": int(n) for k, n in s.execute(q)}

    vs = count_by(func.coalesce(Vehicle.status, C.VS_UNKNOWN), "vstatus")
    total = int(s.scalar(f.select(func.count(Event.id))) or 0)
    return {"total": total, "direction": count_by(Event.direction, "direction"),
            "types": count_by(Event.vehicle_type, "types"), "vstatus": vs,
            "cameras": count_by(Event.camera_id, "cameras")}


def cam_names(s: Session) -> dict[int, str]:
    return {c.id: c.name for c in s.scalars(select(Camera))}


def vehicles_by_id(s: Session, ids: set[int]) -> dict[int, Vehicle]:
    if not ids:
        return {}
    return {v.id: v for v in s.scalars(select(Vehicle).where(Vehicle.id.in_(ids)))}


def visits_in_range(s: Session, vehicle_id: int, a: float, b: float) -> list[dict[str, Any]]:
    rows = s.scalars(select(Visit).where(Visit.vehicle_id == vehicle_id, or_(
        and_(Visit.entry_ts >= a, Visit.entry_ts < b), and_(Visit.exit_ts >= a, Visit.exit_ts < b),
        and_(Visit.entry_ts < a, Visit.exit_ts.is_(None), Visit.status == C.VISIT_INSIDE)))
        .order_by(func.coalesce(Visit.entry_ts, Visit.exit_ts))).all()
    return [visit_dict(v) for v in rows]


def visit_dict(v: Visit) -> dict[str, Any]:
    dur = v.duration_sec
    if dur is None and v.status == C.VISIT_INSIDE and v.entry_ts:
        dur = time.time() - v.entry_ts
    return {"id": v.id, "vehicle_id": v.vehicle_id, "entry_event_id": v.entry_event_id,
            "exit_event_id": v.exit_event_id, "entry_ts": v.entry_ts, "exit_ts": v.exit_ts,
            "duration_sec": dur, "status": v.status}


def vehicle_stats(s: Session, vehicle_id: int, days: int = 30) -> dict[str, Any]:
    since = time.time() - days * 86400
    rows = s.execute(select(Event.direction, func.count(Event.id)).where(
        Event.vehicle_id == vehicle_id, Event.ts >= since).group_by(Event.direction)).all()
    by = {d: int(n) for d, n in rows}
    durs = [d for (d,) in s.execute(select(Visit.duration_sec).where(
        Visit.vehicle_id == vehicle_id, Visit.entry_ts >= since, Visit.duration_sec.is_not(None)))]
    day_expr = func.date(Event.ts + 7 * 3600, "unixepoch")
    days_seen = int(s.scalar(select(func.count(func.distinct(day_expr))).where(
        Event.vehicle_id == vehicle_id, Event.ts >= since)) or 0)
    return {"days": days, "entries": by.get(C.DIR_IN, 0), "exits": by.get(C.DIR_OUT, 0),
            "days_seen": days_seen, "visits": len(durs),
            "avg_duration_sec": (sum(durs) / len(durs)) if durs else None,
            "max_duration_sec": max(durs) if durs else None}


def vehicle_dict(v: Vehicle) -> dict[str, Any]:
    from ..plates.parser import format_display

    return {"id": v.id, "plate_norm": v.plate_norm, "plate_display": format_display(v.plate_norm),
            "province": v.province, "vehicle_type": v.vehicle_type, "type_locked": v.type_locked,
            "status": v.status, "owner_name": v.owner_name, "house_no": v.house_no, "phone": v.phone,
            "note": v.note, "first_seen": v.first_seen, "last_seen": v.last_seen}
