"""FastAPI application: API ทั้งหมด + WebSocket + หน้าเว็บ (React build) + PWA"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import frontend_dist
from .auth import ws_user
from .routes_admin import router as admin_router
from .routes_cameras import router as cameras_router
from .routes_events import router as events_router
from .routes_reports import router as reports_router
from .routes_vehicles import router as vehicles_router

log = logging.getLogger(__name__)
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

FALLBACK_HTML = """<!doctype html><html lang="th"><meta charset="utf-8"><title>LPR บ้าน</title>
<body style="font-family:sans-serif;background:#EEF1F7;color:#141A2E;padding:40px">
<h1>LPR บ้าน กำลังทำงาน</h1><p>ยังไม่พบไฟล์หน้าเว็บ (frontend/dist) — รัน <code>npm run build</code> ในโฟลเดอร์ frontend</p>
<p><a href="/docs">API docs</a></p></body></html>"""


def create_app(ctx, manage_lifecycle: bool = True) -> FastAPI:  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        ctx.hub.bind(asyncio.get_running_loop())
        if manage_lifecycle:
            ctx.start()
        yield
        if manage_lifecycle:
            ctx.stop()

    app = FastAPI(title="LPR บ้าน API", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx

    @app.middleware("http")
    async def guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        # กัน CSRF: คำขอที่แก้ไขข้อมูลต้องมี header นี้ (เว็บอื่นส่งข้ามโดเมนแบบมี header ไม่ได้)
        if request.method in UNSAFE and request.url.path.startswith("/api/") and \
                request.headers.get("x-lpr") != "1":
            return JSONResponse({"detail": "คำขอไม่ถูกต้อง"}, status_code=403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.url.path.startswith("/api/") and "cache-control" not in resp.headers:
            resp.headers["Cache-Control"] = "no-store"
        return resp

    for r in (admin_router, events_router, vehicles_router, cameras_router, reports_router):
        app.include_router(r)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        user = ws_user(ctx, ws)
        if user is None:
            await ws.close(code=4401)
            return
        await ws.accept()
        await ctx.hub.add(ws)
        try:
            await ws.send_json({"type": "hello", "user": user.username,
                                "cameras": {str(k): v for k, v in ctx.cameras.all_status().items()}})
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text('{"type":"pong"}')
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            ctx.hub.remove(ws)

    dist = frontend_dist()
    index = dist / "index.html"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/sw.js", include_in_schema=False)
    def sw() -> Any:
        p = dist / "sw.js"
        if not p.exists():
            return JSONResponse({"detail": "not found"}, 404)
        return FileResponse(p, media_type="application/javascript",
                            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Any:
        if path.startswith("api/"):
            return JSONResponse({"detail": "ไม่พบ"}, status_code=404)
        f = (dist / path).resolve() if path else index
        try:
            f.relative_to(dist.resolve())
        except ValueError:
            f = index
        if path and f.is_file():
            headers = {"Cache-Control": "no-cache"} if f.suffix in (".webmanifest", ".json", ".html") else {}
            return FileResponse(f, headers=headers)
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return HTMLResponse(FALLBACK_HTML)

    return app


def static_root() -> Path:
    return frontend_dist()
