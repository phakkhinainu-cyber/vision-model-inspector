"""เหตุการณ์เข้า-ออก: รายการ (ไทม์ไลน์), จำนวนตามหมวด, รายละเอียด, ภาพ/คลิป, แก้ไข, ลบ, บันทึกด้วยมือ, ส่งออก, คิวรอตรวจสอบ"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from .. import constants as C
from ..db.models import Event, Vehicle
from ..events.service import audit
from ..export import EVENT_COLUMNS, TZ, event_row, th_date, to_csv, to_pdf, to_xlsx
from .auth import CurrentUser, current_user, get_ctx, require_admin
from .queries import (EventFilter, cam_names, facets, list_events, today_range, vehicle_dict, vehicle_stats,
                      vehicles_by_id, visits_in_range)

router = APIRouter(prefix="/api", tags=["events"])


def filters(date_from: str | None = None, date_to: str | None = None, ts_from: float | None = None,
            ts_to: float | None = None, q: str | None = None, direction: str | None = None,
            types: str | None = None, vstatus: str | None = None, cameras: str | None = None,
            review: str | None = None, vehicle_id: int | None = None) -> EventFilter:
    return EventFilter(date_from, date_to, ts_from, ts_to, q, direction, types, vstatus, cameras, review, vehicle_id)


def _dicts(ctx, s, rows: list[Event]) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    cams = cam_names(s)
    vs = vehicles_by_id(s, {e.vehicle_id for e in rows if e.vehicle_id})
    out = []
    for e in rows:
        d = ctx.events.event_dict(s, e, cams, vs)
        d.pop("_thumb_rel", None)
        d.pop("_full_rel", None)
        out.append(d)
    return out


@router.get("/events")
def get_events(f: EventFilter = Depends(filters), limit: int = Query(100, ge=1, le=500), cursor: str | None = None,
               ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        rows, nxt = list_events(s, f, limit, cursor)
        return {"items": _dicts(ctx, s, rows), "next_cursor": nxt}


@router.get("/events/facets")
def get_facets(f: EventFilter = Depends(filters), ctx=Depends(get_ctx),
               _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        return facets(s, f)


@router.get("/events/{event_id}")
def get_event(event_id: int, ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        ev = s.get(Event, event_id)
        if ev is None:
            raise HTTPException(404, "ไม่พบเหตุการณ์")
        d = _dicts(ctx, s, [ev])[0]
        vehicle = None
        if ev.vehicle_id:
            v = s.get(Vehicle, ev.vehicle_id)
            if v is not None:
                a, b = today_range()
                vehicle = {**vehicle_dict(v), "visits_today": visits_in_range(s, v.id, a, b),
                           "stats_30d": vehicle_stats(s, v.id, 30)}
        return {"event": d, "vehicle": vehicle}


@router.get("/events/{event_id}/media/{kind}")
def get_media(event_id: int, kind: str, ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        ev = s.get(Event, event_id)
        if ev is None:
            raise HTTPException(404, "ไม่พบเหตุการณ์")
        rel = {"full": ev.image_full_path, "plate": ev.image_plate_path, "thumb": ev.image_thumb_path or
               ev.image_full_path, "clip": ev.clip_path}.get(kind)
    p = ctx.events.abs_path(rel or "")
    if p is None:
        raise HTTPException(404, "ไม่มีไฟล์ (อาจถูกลบตามระยะเก็บภาพ)")
    media = "video/webm" if p.suffix == ".webm" else ("video/mp4" if p.suffix == ".mp4" else "image/jpeg")
    return FileResponse(p, media_type=media, headers={"Cache-Control": "private, max-age=86400"})


class EventPatch(BaseModel):
    plate: str | None = None
    province: str | None = None
    vehicle_type: str | None = None
    direction: str | None = None
    review_status: str | None = None
    note: str | None = None


@router.patch("/events/{event_id}")
def patch_event(event_id: int, body: EventPatch, ctx=Depends(get_ctx),
                user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    try:
        out = ctx.events.edit_event(event_id, body.model_dump(exclude_unset=True), user.username)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    out.pop("_thumb_rel", None)
    out.pop("_full_rel", None)
    return out


@router.delete("/events/{event_id}")
def del_event(event_id: int, ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    try:
        ctx.events.delete_event(event_id, user.username)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True}


class ManualEvent(BaseModel):
    camera_id: int | None = None
    direction: str = C.DIR_IN
    plate: str = ""
    province: str = ""
    vehicle_type: str = C.VT_OTHER
    note: str = ""
    ts: float | None = None
    snapshot: bool = True


@router.post("/events/manual")
def manual_event(body: ManualEvent, ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    jpg = b""
    if body.camera_id and body.snapshot:
        r = ctx.cameras.request(body.camera_id, {"cmd": "snapshot"}, timeout=5)
        jpg = r.get("jpeg") or b""
    try:
        out = ctx.events.manual_event(body.model_dump(), user.username, jpg)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    out.pop("_thumb_rel", None)
    out.pop("_full_rel", None)
    return out


# ------------------------------------------------------------------ review queue
@router.get("/review")
def review_queue(limit: int = Query(200, le=1000), ctx=Depends(get_ctx),
                 _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        rows = list(s.scalars(select(Event).where(Event.review_status.in_([C.REVIEW_PENDING, C.REVIEW_UNREAD]))
                              .order_by(Event.ts.desc()).limit(limit)))
        total = int(s.scalar(select(func.count(Event.id)).where(
            Event.review_status.in_([C.REVIEW_PENDING, C.REVIEW_UNREAD]))) or 0)
        return {"items": _dicts(ctx, s, rows), "total": total}


# ------------------------------------------------------------------ export
def _export_rows(ctx, f: EventFilter, limit: int = 100000) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        rows, _ = list_events(s, f, limit, None)
        return list(reversed(_dicts(ctx, s, rows)))


def _period_text(f: EventFilter, items: list[dict[str, Any]]) -> str:
    if f.date_from or f.date_to:
        a = th_date(datetime.fromisoformat(f.date_from).replace(tzinfo=TZ).timestamp()) if f.date_from else "-"
        b = th_date(datetime.fromisoformat(f.date_to).replace(tzinfo=TZ).timestamp()) if f.date_to else "-"
        return a if a == b else f"{a} – {b}"
    if items:
        return f"{th_date(items[0]['ts'])} – {th_date(items[-1]['ts'])}"
    return "-"


@router.get("/export/events.{fmt}")
def export_events(fmt: str, f: EventFilter = Depends(filters), ctx=Depends(get_ctx),
                  user: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    if fmt not in ("csv", "xlsx", "pdf"):
        raise HTTPException(404, "ไม่รองรับรูปแบบนี้")
    items = _export_rows(ctx, f)
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M")
    with ctx.db.session() as s:
        audit(s, user.username, "ส่งออกข้อมูล", f"{fmt.upper()} {len(items)} รายการ")
    if fmt == "csv":
        data, mt = to_csv(EVENT_COLUMNS, (event_row(e) for e in items)), "text/csv; charset=utf-8"
    elif fmt == "xlsx":
        data = to_xlsx(EVENT_COLUMNS, (event_row(e) for e in items), "บันทึกเข้า-ออก")
        mt = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        n_in = sum(1 for e in items if e["direction"] == C.DIR_IN)
        summary = [("ทั้งหมด", f"{len(items):,}"), ("เข้า", f"{n_in:,}"), ("ออก", f"{len(items) - n_in:,}"),
                   ("รถไม่ซ้ำ", f"{len({e['vehicle_id'] for e in items if e['vehicle_id']}):,}"),
                   ("อ่านไม่ได้", f"{sum(1 for e in items if not e['plate_norm']):,}"),
                   ("รอตรวจสอบ", f"{sum(1 for e in items if e['review_status'] == C.REVIEW_PENDING):,}")]
        house = ctx.settings.get("house_name")
        data = to_pdf(f"รายงานสมุดบันทึกเข้า-ออก · {house}", f"ช่วงเวลา {_period_text(f, items)} · พิมพ์เมื่อ "
                      f"{th_date(datetime.now(TZ).timestamp())} {datetime.now(TZ):%H:%M} น. โดย {user.username}",
                      summary, items)
        mt = "application/pdf"
    name = f"lpr-events-{stamp}.{fmt}"
    return Response(data, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{name}"'})
