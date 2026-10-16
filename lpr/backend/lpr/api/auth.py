"""ล็อกอิน: รหัสผ่าน argon2, session token (จำเครื่องได้ตามวันที่ตั้ง), จำกัดจำนวนครั้งที่ล็อกอินผิด, สิทธิ์ admin/viewer"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, WebSocket
from sqlalchemy import delete, func, select

from .. import constants as C
from ..db.models import SessionRow, User

COOKIE = "lpr_session"
_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def validate_password(pw: str) -> None:
    if len(pw or "") < 6:
        raise HTTPException(400, "รหัสผ่านต้องยาวอย่างน้อย 6 ตัวอักษร")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class CurrentUser:
    id: int
    username: str
    role: str
    display_name: str

    @property
    def is_admin(self) -> bool:
        return self.role == C.ROLE_ADMIN


class LoginLimiter:
    """ล็อกชั่วคราวเมื่อล็อกอินผิดเกินกำหนด (แยกตาม IP + ชื่อผู้ใช้ และตาม IP รวม)"""

    def __init__(self) -> None:
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _keys(self, ip: str, username: str) -> list[str]:
        return [f"{ip}|{username.lower()}", f"{ip}|*"]

    def locked_for(self, ip: str, username: str, max_attempts: int, lock_minutes: int) -> float:
        now = time.time()
        window = lock_minutes * 60
        with self._lock:
            worst = 0.0
            for i, k in enumerate(self._keys(ip, username)):
                limit = max_attempts if i == 0 else max_attempts * 3
                fails = [t for t in self._fails.get(k, []) if now - t < window]
                self._fails[k] = fails
                if len(fails) >= limit:
                    worst = max(worst, fails[-limit] + window - now)
            return worst

    def fail(self, ip: str, username: str) -> None:
        with self._lock:
            for k in self._keys(ip, username):
                self._fails.setdefault(k, []).append(time.time())

    def reset(self, ip: str, username: str) -> None:
        with self._lock:
            self._fails.pop(self._keys(ip, username)[0], None)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")  # tailscale serve ส่งต่อมาจาก 127.0.0.1
    if fwd and request.client and request.client.host in ("127.0.0.1", "::1"):
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def create_session(ctx, user_id: int, remember: bool, user_agent: str) -> tuple[str, int | None]:  # type: ignore[no-untyped-def]
    token = secrets.token_urlsafe(32)
    days = int(ctx.settings.get("remember_days"))
    life = days * 86400 if remember else 12 * 3600
    now = time.time()
    with ctx.db.session() as s:
        s.execute(delete(SessionRow).where(SessionRow.expires_at < now))
        s.add(SessionRow(token_hash=token_hash(token), user_id=user_id, created_at=now, expires_at=now + life,
                         user_agent=user_agent[:300]))
    return token, (life if remember else None)


def _lookup(ctx, token: str | None) -> CurrentUser | None:  # type: ignore[no-untyped-def]
    if not token:
        return None
    with ctx.db.session() as s:
        row = s.execute(select(User).join(SessionRow, SessionRow.user_id == User.id)
                        .where(SessionRow.token_hash == token_hash(token), SessionRow.expires_at > time.time())).scalar()
        if row is None:
            return None
        return CurrentUser(row.id, row.username, row.role, row.display_name or row.username)


def _token_from(request: Request) -> str | None:
    tok = request.cookies.get(COOKIE)
    if tok:
        return tok
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


def get_ctx(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.ctx


def current_user(request: Request, ctx=Depends(get_ctx)) -> CurrentUser:  # type: ignore[no-untyped-def]
    u = _lookup(ctx, _token_from(request))
    if u is None:
        raise HTTPException(401, "กรุณาเข้าสู่ระบบ")
    return u


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(403, "ต้องเป็นผู้ดูแลระบบ (admin) จึงทำรายการนี้ได้")
    return user


def ws_user(ctx, ws: WebSocket) -> CurrentUser | None:  # type: ignore[no-untyped-def]
    return _lookup(ctx, ws.cookies.get(COOKIE) or ws.query_params.get("token"))


def user_count(ctx) -> int:  # type: ignore[no-untyped-def]
    with ctx.db.session() as s:
        return int(s.scalar(select(func.count(User.id))) or 0)
