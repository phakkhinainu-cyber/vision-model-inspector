"""รายงาน: สรุปรายวัน/รายเดือน, จำนวนเข้า-ออกรายชั่วโมง, รถที่อยู่นานผิดปกติ"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select

from .. import constants as C
from ..db.models import Event, Vehicle, Visit
from .auth import CurrentUser, current_user, get_ctx
from .queries import TZ, day_range, vehicle_dict, visit_dict

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/summary")
def summary(date_from: str | None = None, date_to: str | None = None, ctx=Depends(get_ctx),
            _: CurrentUser = Depends(current_user)) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    if not date_from:
        date_from = datetime.now(TZ).strftime("%Y-%m-%d")
    if not date_to:
        date_to = date_from
    a, b = day_range(date_from, date_to)
    hours = [{"hour": h, "in": 0, "out": 0} for h in range(24)]
    days: dict[str, dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0})
    with ctx.db.session() as s:
        rows = s.execute(select(Event.ts, Event.direction, Event.vehicle_type, Event.review_status, Event.vehicle_id,
                                Vehicle.status).outerjoin(Vehicle, Vehicle.id == Event.vehicle_id)
                         .where(Event.ts >= a, Event.ts < b)).all()
        by_type: dict[str, int] = defaultdict(int)
        by_status: dict[str, int] = defaultdict(int)
        by_review: dict[str, int] = defaultdict(int)
        vehicles = set()
        for ts, d, vt, rv, vid, vst in rows:
            dt = datetime.fromtimestamp(ts, TZ)
            k = "in" if d == C.DIR_IN else "out"
            hours[dt.hour][k] += 1
            days[dt.strftime("%Y-%m-%d")][k] += 1
            by_type[vt or C.VT_OTHER] += 1
            by_status[vst or C.VS_UNKNOWN] += 1
            by_review[rv] += 1
            if vid:
                vehicles.add(vid)
        durs = [d for (d,) in s.execute(select(Visit.duration_sec).where(
            Visit.exit_ts >= a, Visit.exit_ts < b, Visit.duration_sec.is_not(None)))]
    # ทุกวันในช่วง (รวมวันที่ไม่มีรถ)
    series = []
    d0 = datetime.fromisoformat(date_from)
    d1 = datetime.fromisoformat(date_to)
    while d0 <= d1 and len(series) < 400:
        key = d0.strftime("%Y-%m-%d")
        series.append({"date": key, **days.get(key, {"in": 0, "out": 0})})
        d0 += timedelta(days=1)
    n_in = sum(h["in"] for h in hours)
    return {"date_from": date_from, "date_to": date_to, "total": len(rows), "in": n_in, "out": len(rows) - n_in,
            "unique_vehicles": len(vehicles), "unread": by_review.get(C.REVIEW_UNREAD, 0),
            "pending": by_review.get(C.REVIEW_PENDING, 0), "hours": hours, "days": series,
            "by_type": dict(by_type), "by_status": dict(by_status),
            "avg_duration_sec": (sum(durs) / len(durs)) if durs else None, "visits_closed": len(durs)}


@router.get("/long-stay")
def long_stay(hours: float = Query(12, ge=0.1), days: int = Query(30, ge=1, le=366), ctx=Depends(get_ctx),
              _: CurrentUser = Depends(current_user)) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """รถที่อยู่นานผิดปกติ: อยู่เกิน X ชั่วโมง (รวมคันที่ยังอยู่ตอนนี้)"""
    now = time.time()
    lim = hours * 3600
    since = now - days * 86400
    with ctx.db.session() as s:
        q = (select(Visit, Vehicle).join(Vehicle, Vehicle.id == Visit.vehicle_id)
             .where(Visit.entry_ts >= since, or_(Visit.duration_sec > lim,
                                                  and_(Visit.exit_ts.is_(None), Visit.entry_ts < now - lim)))
             .order_by(func.coalesce(Visit.duration_sec, now - Visit.entry_ts).desc()).limit(300))
        items = [{**visit_dict(v), "vehicle": vehicle_dict(veh)} for v, veh in s.execute(q).all()]
    return {"hours": hours, "days": days, "items": items}
