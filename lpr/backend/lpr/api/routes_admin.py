"""ล็อกอิน/ผู้ใช้, ค่าตั้งค่า, บันทึกการใช้งาน (audit log), สำรองข้อมูล, แจ้งเตือน, สถานะระบบ"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from .. import APP_NAME, __version__
from .. import constants as C
from ..config import MODEL_FILES, find_model, set_home_pointer
from ..db.models import AuditLog, Camera, Event, PushSubscription, SessionRow, User
from ..events.service import audit
from ..maintenance import disk_usage
from ..notify import ensure_vapid
from ..selftest import demo_video
from ..settings import G_GENERAL
from ..vision.runtime import available_providers, gpu_adapters
from .auth import (COOKIE, CurrentUser, client_ip, create_session, current_user, get_ctx, hash_password,
                   require_admin, token_hash, user_count, validate_password, verify_password)

router = APIRouter(prefix="/api", tags=["admin"])


# ------------------------------------------------------------------ auth
@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": APP_NAME, "version": __version__, "ts": time.time()}


@router.get("/auth/status")
def auth_status(request: Request, ctx=Depends(get_ctx)):  # type: ignore[no-untyped-def]
    from .auth import _lookup, _token_from

    u = _lookup(ctx, _token_from(request))
    return {"setup_required": user_count(ctx) == 0, "house_name": ctx.settings.get("house_name"),
            "user": u.__dict__ if u else None}


class SetupIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    house_name: str = ""


def _set_cookie(resp: JSONResponse, request: Request, token: str, max_age: int | None) -> None:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie(COOKIE, token, max_age=max_age, httponly=True, samesite="lax", secure=secure, path="/")


@router.post("/auth/setup")
def setup(body: SetupIn, request: Request, ctx=Depends(get_ctx)):  # type: ignore[no-untyped-def]
    """ครั้งแรกที่เปิดโปรแกรม: สร้างผู้ดูแลระบบ"""
    if user_count(ctx) > 0:
        raise HTTPException(409, "ตั้งค่าเริ่มต้นไปแล้ว")
    name = body.username.strip()
    if not name:
        raise HTTPException(400, "กรุณากรอกชื่อผู้ใช้")
    validate_password(body.password)
    with ctx.db.session() as s:
        u = User(username=name, password_hash=hash_password(body.password), role=C.ROLE_ADMIN,
                 display_name=body.display_name or name, created_at=time.time())
        s.add(u)
        s.flush()
        uid = u.id
        audit(s, name, "ตั้งค่าเริ่มต้น", "สร้างผู้ดูแลระบบ")
    if body.house_name.strip():
        ctx.settings.update({"house_name": body.house_name.strip()})
    token, age = create_session(ctx, uid, True, request.headers.get("user-agent", ""))
    resp = JSONResponse({"ok": True})
    _set_cookie(resp, request, token, age)
    return resp


class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = True


@router.post("/auth/login")
def login(body: LoginIn, request: Request, ctx=Depends(get_ctx)):  # type: ignore[no-untyped-def]
    ip = client_ip(request)
    name = body.username.strip()
    wait = ctx.limiter.locked_for(ip, name, int(ctx.settings.get("login_max_attempts")),
                                  int(ctx.settings.get("login_lock_minutes")))
    if wait > 0:
        raise HTTPException(429, f"ล็อกอินผิดหลายครั้ง กรุณารอ {int(wait // 60) + 1} นาที")
    with ctx.db.session() as s:
        u = s.scalar(select(User).where(func.lower(User.username) == name.lower()))
        ok = u is not None and verify_password(u.password_hash, body.password)
        if not ok:
            ctx.limiter.fail(ip, name)
            s.add(AuditLog(ts=time.time(), user=name or "?", action="ล็อกอินไม่สำเร็จ", detail=ip))
        else:
            uid = u.id  # type: ignore[union-attr]
            s.add(AuditLog(ts=time.time(), user=u.username, action="ล็อกอิน", detail=ip))  # type: ignore[union-attr]
    if not ok:
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    ctx.limiter.reset(ip, name)
    token, age = create_session(ctx, uid, body.remember, request.headers.get("user-agent", ""))
    resp = JSONResponse({"ok": True})
    _set_cookie(resp, request, token, age)
    return resp


@router.post("/auth/logout")
def logout(request: Request, ctx=Depends(get_ctx)):  # type: ignore[no-untyped-def]
    tok = request.cookies.get(COOKIE)
    if tok:
        with ctx.db.session() as s:
            s.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash(tok)))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.get("/auth/me")
def me(user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return user.__dict__


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/auth/password")
def change_password(body: PasswordIn, ctx=Depends(get_ctx), user: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    validate_password(body.new_password)
    with ctx.db.session() as s:
        u = s.get(User, user.id)
        if u is None or not verify_password(u.password_hash, body.old_password):
            raise HTTPException(400, "รหัสผ่านเดิมไม่ถูกต้อง")
        u.password_hash = hash_password(body.new_password)
        audit(s, user.username, "เปลี่ยนรหัสผ่าน", "")
    return {"ok": True}


# ------------------------------------------------------------------ users
class UserIn(BaseModel):
    username: str | None = None
    password: str | None = None
    role: str | None = None
    display_name: str | None = None


def _user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "username": u.username, "role": u.role, "display_name": u.display_name,
            "created_at": u.created_at}


@router.get("/users")
def list_users(ctx=Depends(get_ctx), _: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        return {"items": [_user_out(u) for u in s.scalars(select(User).order_by(User.id))]}


@router.post("/users")
def create_user(body: UserIn, ctx=Depends(get_ctx), admin: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    name = (body.username or "").strip()
    if not name:
        raise HTTPException(400, "กรุณากรอกชื่อผู้ใช้")
    validate_password(body.password or "")
    role = body.role or C.ROLE_VIEWER
    if role not in (C.ROLE_ADMIN, C.ROLE_VIEWER):
        raise HTTPException(400, "สิทธิ์ไม่ถูกต้อง")
    with ctx.db.session() as s:
        if s.scalar(select(User).where(func.lower(User.username) == name.lower())):
            raise HTTPException(409, "มีชื่อผู้ใช้นี้แล้ว")
        u = User(username=name, password_hash=hash_password(body.password or ""), role=role,
                 display_name=body.display_name or name, created_at=time.time())
        s.add(u)
        s.flush()
        audit(s, admin.username, "เพิ่มผู้ใช้", f"{name} ({role})")
        return _user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserIn, ctx=Depends(get_ctx), admin: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        u = s.get(User, user_id)
        if u is None:
            raise HTTPException(404, "ไม่พบผู้ใช้")
        if body.role and body.role != u.role:
            if body.role not in (C.ROLE_ADMIN, C.ROLE_VIEWER):
                raise HTTPException(400, "สิทธิ์ไม่ถูกต้อง")
            if u.role == C.ROLE_ADMIN and _admins(s) <= 1:
                raise HTTPException(400, "ต้องมีผู้ดูแลระบบอย่างน้อย 1 คน")
            u.role = body.role
        if body.display_name is not None:
            u.display_name = body.display_name
        if body.password:
            validate_password(body.password)
            u.password_hash = hash_password(body.password)
            s.execute(delete(SessionRow).where(SessionRow.user_id == u.id))
        audit(s, admin.username, "แก้ไขผู้ใช้", f"{u.username}: {', '.join(body.model_dump(exclude_unset=True, exclude={'password'}))}"
              + (" + รีเซ็ตรหัสผ่าน" if body.password else ""))
        return _user_out(u)


def _admins(s) -> int:  # type: ignore[no-untyped-def]
    return int(s.scalar(select(func.count(User.id)).where(User.role == C.ROLE_ADMIN)) or 0)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, ctx=Depends(get_ctx), admin: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    if user_id == admin.id:
        raise HTTPException(400, "ลบบัญชีของตัวเองไม่ได้")
    with ctx.db.session() as s:
        u = s.get(User, user_id)
        if u is None:
            raise HTTPException(404, "ไม่พบผู้ใช้")
        if u.role == C.ROLE_ADMIN and _admins(s) <= 1:
            raise HTTPException(400, "ต้องมีผู้ดูแลระบบอย่างน้อย 1 คน")
        audit(s, admin.username, "ลบผู้ใช้", u.username)
        s.delete(u)
    return {"ok": True}


# ------------------------------------------------------------------ settings
@router.get("/settings")
def get_settings(ctx=Depends(get_ctx), user: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    items = ctx.settings.schema()
    if not user.is_admin:
        items = [i for i in items if i["group"] == G_GENERAL]
    return {"items": items, "restart_required": sorted(ctx.restart_required), "home": str(ctx.paths.home),
            "backup_dir": str(ctx.maintenance.backup_dir())}


@router.put("/settings")
def put_settings(body: dict[str, Any], ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    try:
        changed = ctx.settings.update(body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if changed:
        from ..settings import DEF_BY_KEY

        shown = {k: ("••••" if DEF_BY_KEY.get(k) and DEF_BY_KEY[k].secret else v) for k, v in changed.items()}
        with ctx.db.session() as s:
            audit(s, user.username, "แก้ไขค่าตั้งค่า", ", ".join(f"{k}={v}" for k, v in shown.items()))
        ctx.hub.publish({"type": "settings", "changed": list(changed)})
    return {"changed": list(changed), "restart_required": sorted(ctx.restart_required)}


class StorageIn(BaseModel):
    path: str
    copy_data: bool = True


@router.post("/system/storage")
def change_storage(body: StorageIn, ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    """ย้ายที่เก็บข้อมูล (มีผลหลังรีสตาร์ตโปรแกรม)"""
    dst = Path(body.path.strip())
    if not dst.is_absolute():
        raise HTTPException(400, "กรุณาระบุตำแหน่งแบบเต็ม เช่น E:\\LPR")
    if dst.resolve() == ctx.paths.home.resolve():
        raise HTTPException(400, "เป็นตำแหน่งเดิม")
    try:
        (dst / "data").mkdir(parents=True, exist_ok=True)
        probe = dst / "data" / ".write_test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        raise HTTPException(400, f"เขียนไฟล์ที่ตำแหน่งนี้ไม่ได้: {e}") from e

    def work() -> None:
        if body.copy_data:
            ctx.db.backup_to(dst / "data" / "lpr.db")
            if ctx.paths.images.exists():
                shutil.copytree(ctx.paths.images, dst / "data" / "images", dirs_exist_ok=True)
            for f in ("camera_secrets.json", ".camkey"):
                if (ctx.paths.data / f).exists():
                    shutil.copy2(ctx.paths.data / f, dst / "data" / f)
        set_home_pointer(dst)
        ctx.restart_required.add("storage")
        ctx.hub.publish({"type": "alert", "level": "info",
                         "message": f"ย้ายที่เก็บข้อมูลไปที่ {dst} แล้ว กรุณารีสตาร์ตโปรแกรม"})

    with ctx.db.session() as s:
        audit(s, user.username, "ย้ายที่เก็บข้อมูล", f"{ctx.paths.home} -> {dst} (คัดลอก={body.copy_data})")
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "restart_required": True}


# ------------------------------------------------------------------ audit & backup
@router.get("/audit")
def get_audit(page: int = Query(1, ge=1), size: int = Query(100, le=500), ctx=Depends(get_ctx),
              _: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        rows = s.scalars(select(AuditLog).order_by(AuditLog.ts.desc()).offset((page - 1) * size).limit(size))
        total = int(s.scalar(select(func.count(AuditLog.id))) or 0)
        return {"items": [{"id": r.id, "ts": r.ts, "user": r.user, "action": r.action, "detail": r.detail}
                          for r in rows], "total": total}


@router.post("/backup/run")
def run_backup(ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    try:
        return ctx.maintenance.run_backup(user.username)
    except OSError as e:
        raise HTTPException(500, f"สำรองข้อมูลไม่สำเร็จ: {e}") from e


@router.get("/backup/list")
def list_backups(ctx=Depends(get_ctx), _: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    return {"items": ctx.maintenance.list_backups(), "dir": str(ctx.maintenance.backup_dir())}


@router.post("/maintenance/cleanup")
def run_cleanup(ctx=Depends(get_ctx), user: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    r = ctx.maintenance.cleanup()
    with ctx.db.session() as s:
        audit(s, user.username, "ลบข้อมูลเก่า", f"ไฟล์ {r['files']} แถว {r['rows']}")
    return r


# ------------------------------------------------------------------ push & notify
@router.get("/push/key")
def push_key(ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    return {"public_key": ensure_vapid(ctx.settings), "enabled": bool(ctx.settings.get("webpush_enabled"))}


class SubIn(BaseModel):
    endpoint: str
    keys: dict[str, str]


@router.post("/push/subscribe")
def push_subscribe(body: SubIn, ctx=Depends(get_ctx), user: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        row = s.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
        if row is None:
            row = PushSubscription(endpoint=body.endpoint, created_at=time.time(), user_id=user.id,
                                   p256dh=body.keys.get("p256dh", ""), auth=body.keys.get("auth", ""))
            s.add(row)
        else:
            row.user_id, row.p256dh, row.auth = user.id, body.keys.get("p256dh", ""), body.keys.get("auth", "")
    return {"ok": True}


@router.post("/push/unsubscribe")
def push_unsubscribe(body: SubIn, ctx=Depends(get_ctx), _: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        s.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    return {"ok": True}


class NotifyTest(BaseModel):
    channel: str


@router.post("/notify/test")
def notify_test(body: NotifyTest, ctx=Depends(get_ctx), _: CurrentUser = Depends(require_admin)):  # type: ignore[no-untyped-def]
    try:
        return {"result": ctx.notifier.test(body.channel)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"ส่งไม่สำเร็จ: {e}") from e


# ------------------------------------------------------------------ system
@router.get("/system/status")
def system_status(ctx=Depends(get_ctx), user: CurrentUser = Depends(current_user)):  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        cams = [{"id": c.id, "name": c.name, "role": c.role, "enabled": c.enabled,
                 "status": ctx.cameras.status_of(c.id)} for c in s.scalars(select(Camera).order_by(Camera.sort_order,
                                                                                                   Camera.id))]
        pending = int(s.scalar(select(func.count(Event.id)).where(
            Event.review_status.in_([C.REVIEW_PENDING, C.REVIEW_UNREAD]))) or 0)
    du = disk_usage(ctx.paths.home)
    alerts = list(ctx.maintenance.alerts.values())
    for name, err in ctx.notifier.last_errors.items():
        alerts.append(f"แจ้งเตือน {name} ส่งไม่สำเร็จ: {err}")
    out: dict[str, Any] = {
        "app": APP_NAME, "version": __version__, "house_name": ctx.settings.get("house_name"), "cameras": cams,
        "camera_count": sum(1 for c in cams if c["enabled"]), "pending_review": pending, "disk": du,
        "alerts": alerts, "restart_required": sorted(ctx.restart_required), "user": user.__dict__,
    }
    if user.is_admin:
        out.update(home=str(ctx.paths.home), credentials=ctx.creds.backend, providers=available_providers(),
                   gpus=[g["name"] for g in gpu_adapters()],
                   models={k: bool(find_model(ctx.paths, k)) for k in MODEL_FILES},
                   last_backup=ctx.maintenance.last_backup, pid=os.getpid(),
                   demo_video=str(demo_video()) if demo_video() else None)
    return out
