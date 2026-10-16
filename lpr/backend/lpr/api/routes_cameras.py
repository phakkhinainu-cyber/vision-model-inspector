"""กล้อง: เพิ่ม/แก้ RTSP, ทดสอบการเชื่อมต่อ, ภาพสด (MJPEG), ภาพนิ่ง, วาด ROI/เส้นเสมือน, บทบาท, จับภาพเดี๋ยวนี้"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .. import constants as C
from ..camera.stream import mask_url, probe
from ..camera.worker import camera_dict
from ..db.models import Camera
from ..events.service import audit
from ..vision.geometry import parse_points
from .auth import CurrentUser, current_user, get_ctx, require_admin

router = APIRouter(prefix="/api/cameras", tags=["cameras"])
MAX_CAMERAS = 8


def cam_out(ctx, c: Camera) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {"id": c.id, "name": c.name, "rtsp_main": mask_url(c.rtsp_main), "rtsp_sub": mask_url(c.rtsp_sub),
            "username": c.username, "has_password": bool(c.username and ctx.creds.get(c.id)), "role": c.role,
            "roi_polygon": parse_points(c.roi_polygon), "line_coords": parse_points(c.line_coords),
            "line_direction": c.line_direction, "enabled": c.enabled, "sort_order": c.sort_order,
            "status": ctx.cameras.status_of(c.id)}


@router.get("")
def list_cameras(ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        return {"items": [cam_out(ctx, c) for c in s.scalars(select(Camera).order_by(Camera.sort_order, Camera.id))],
                "max": MAX_CAMERAS}


class CameraIn(BaseModel):
    name: str | None = None
    rtsp_main: str | None = None
    rtsp_sub: str | None = None
    username: str | None = None
    password: str | None = None
    role: str | None = None
    roi_polygon: list[list[float]] | None = None
    line_coords: list[list[float]] | None = None
    line_direction: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None


def _validate(body: CameraIn) -> None:
    if body.role is not None and body.role not in C.CAMERA_ROLES:
        raise HTTPException(400, "บทบาทกล้องไม่ถูกต้อง")
    if body.line_direction is not None and body.line_direction not in (C.LINE_POS_IN, C.LINE_NEG_IN):
        raise HTTPException(400, "ทิศทางเส้นไม่ถูกต้อง")
    if body.line_coords is not None and len(body.line_coords) not in (0, 2):
        raise HTTPException(400, "เส้นเสมือนต้องมี 2 จุด")
    if body.roi_polygon is not None and 0 < len(body.roi_polygon) < 3:
        raise HTTPException(400, "โซน ROI ต้องมีอย่างน้อย 3 จุด")


def _strip_password(url: str) -> tuple[str, str, str]:
    """ถ้าผู้ใช้วางลิงก์ที่มีรหัสผ่านมาด้วย แยกรหัสผ่านออกไปเก็บใน Credential Manager"""
    if "://" not in url:
        return url, "", ""
    scheme, rest = url.split("://", 1)
    host_part = rest.split("/", 1)[0]
    if "@" not in host_part:
        return url, "", ""
    cred, after = rest.split("@", 1)
    from urllib.parse import unquote

    user, _, pw = cred.partition(":")
    if pw == "***":
        pw = ""
    return f"{scheme}://{after}", unquote(user), unquote(pw)


def _save(ctx, c: Camera, body: CameraIn) -> str:  # type: ignore[no-untyped-def]
    data = body.model_dump(exclude_unset=True)
    pw = data.pop("password", None)
    for k in ("rtsp_main", "rtsp_sub"):
        if k in data and data[k] is not None:
            url, u, p = _strip_password(data[k].strip())
            data[k] = url
            if u and not data.get("username"):
                data["username"] = u
            if p and not pw:
                pw = p
    for k, v in data.items():
        if v is None:
            continue
        if k in ("roi_polygon", "line_coords"):
            v = json.dumps(v)
        setattr(c, k, v)
    return pw or ""


@router.post("")
def create_camera(body: CameraIn, ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    _validate(body)
    if not (body.rtsp_main or "").strip():
        raise HTTPException(400, "กรุณากรอกลิงก์ RTSP หรือไฟล์วิดีโอ")
    with ctx.db.session() as s:
        if (s.scalar(select(func.count(Camera.id))) or 0) >= MAX_CAMERAS:
            raise HTTPException(400, f"รองรับกล้องได้สูงสุด {MAX_CAMERAS} ตัว")
        c = Camera(name=body.name or "กล้อง", role=body.role or C.ROLE_BOTH, roi_polygon="[]", line_coords="[]",
                   line_direction=C.LINE_POS_IN, enabled=True, rtsp_sub="", username="")
        pw = _save(ctx, c, body)
        s.add(c)
        s.flush()
        cid = c.id
        audit(s, user.username, "เพิ่มกล้อง", f"#{cid} {c.name} {mask_url(c.rtsp_main)}")
    if pw:
        ctx.creds.set(cid, pw)
    if ctx.start_cameras:
        threading.Thread(target=ctx.cameras.start, args=(cid,), daemon=True).start()
    with ctx.db.session() as s:
        return cam_out(ctx, s.get(Camera, cid))


@router.patch("/{cam_id}")
def update_camera(cam_id: int, body: CameraIn, ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    _validate(body)
    with ctx.db.session() as s:
        c = s.get(Camera, cam_id)
        if c is None:
            raise HTTPException(404, "ไม่พบกล้อง")
        pw = _save(ctx, c, body)
        audit(s, user.username, "แก้ไขกล้อง", f"#{cam_id} {', '.join(body.model_dump(exclude_unset=True, exclude={'password'}))}")
        enabled = c.enabled
    if pw or body.password == "":
        ctx.creds.set(cam_id, pw)
    if ctx.start_cameras:
        def apply() -> None:
            ctx.cameras.stop(cam_id)
            if enabled:
                ctx.cameras.start(cam_id)
        threading.Thread(target=apply, daemon=True).start()
    with ctx.db.session() as s:
        return cam_out(ctx, s.get(Camera, cam_id))


@router.delete("/{cam_id}")
def delete_camera(cam_id: int, ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    ctx.cameras.stop(cam_id)
    with ctx.db.session() as s:
        c = s.get(Camera, cam_id)
        if c is None:
            raise HTTPException(404, "ไม่พบกล้อง")
        audit(s, user.username, "ลบกล้อง", f"#{cam_id} {c.name}")
        s.delete(c)
    ctx.creds.delete(cam_id)
    return {"ok": True}


class TestIn(BaseModel):
    url: str
    username: str = ""
    password: str = ""
    camera_id: int | None = None


@router.post("/test")
async def test_connection(body: TestIn, ctx=Depends(get_ctx), _: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    url, u, p = _strip_password(body.url.strip())
    user = body.username or u
    pw = body.password or p
    if body.camera_id and not pw and user:
        pw = ctx.creds.get(body.camera_id)

    class Row:
        id = 0
        name = ""
        role = C.ROLE_BOTH
        roi_polygon = "[]"
        line_coords = "[]"
        line_direction = C.LINE_POS_IN
        rtsp_main = url
        rtsp_sub = ""
        username = user

    full = camera_dict(Row, pw)["url_main"]
    t0 = time.time()
    r = await asyncio.to_thread(probe, full, 12.0)
    r["seconds"] = round(time.time() - t0, 1)
    if r.get("jpeg"):
        r["image"] = "data:image/jpeg;base64," + base64.b64encode(r.pop("jpeg")).decode()
    return r


@router.get("/{cam_id}/snapshot.jpg")
async def snapshot(cam_id: int, ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    r = await asyncio.to_thread(ctx.cameras.request, cam_id, {"cmd": "snapshot"}, 6.0)
    jpg = r.get("jpeg")
    if not jpg:
        with ctx.db.session() as s:
            c = s.get(Camera, cam_id)
            if c is None:
                raise HTTPException(404, "ไม่พบกล้อง")
            full = camera_dict(c, ctx.creds.get(cam_id) if c.username else "")["url_main"]
        pr = await asyncio.to_thread(probe, full, 10.0)
        jpg = pr.get("jpeg")
        if not jpg:
            raise HTTPException(503, pr.get("error") or r.get("error") or "ไม่ได้รับภาพจากกล้อง")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/{cam_id}/live.mjpg")
async def live(cam_id: int, request: Request, ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    """ภาพสดพร้อมกรอบรถ/โซน/เส้น (MJPEG ~5 fps) ส่งเฉพาะตอนมีคนดู เพื่อประหยัด CPU"""
    boundary = "lprframe"

    async def gen():  # type: ignore[no-untyped-def]
        last_ts = 0.0
        last_ping = 0.0
        idle = 0
        while not await request.is_disconnected():
            now = time.time()
            if now - last_ping > 5:
                ctx.cameras.want_preview(cam_id)
                last_ping = now
            p = ctx.cameras.latest_preview(cam_id)
            if p and p[0] != last_ts:
                last_ts = p[0]
                idle = 0
                yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(p[1])}\r\n\r\n").encode() \
                    + p[1] + b"\r\n"
            else:
                idle += 1
                if idle > 600:
                    break
            await asyncio.sleep(0.1)

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}",
                             headers={"Cache-Control": "no-store"})


class CaptureIn(BaseModel):
    direction: str | None = Field(default=None)


@router.post("/{cam_id}/capture")
async def capture_now(cam_id: int, body: CaptureIn, ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    r = await asyncio.to_thread(ctx.cameras.request, cam_id, {"cmd": "capture", "direction": body.direction}, 15.0)
    if r.get("error"):
        raise HTTPException(503, r["error"])
    with ctx.db.session() as s:
        audit(s, user.username, "จับภาพเดี๋ยวนี้", f"กล้อง #{cam_id}")
    return {"ok": True, "uid": r.get("uid")}


@router.post("/{cam_id}/restart")
def restart(cam_id: int, ctx=Depends(get_ctx), _: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    threading.Thread(target=ctx.cameras.restart, args=(cam_id,), daemon=True).start()
    return {"ok": True}
