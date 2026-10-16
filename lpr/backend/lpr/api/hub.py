"""กระจายข้อความแบบสดไปยังหน้าจอทุกเครื่องผ่าน WebSocket (เรียก publish ได้จากทุก thread)"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: set[WebSocket] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def add(self, ws: WebSocket) -> None:
        self.clients.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    def publish(self, msg: dict[str, Any]) -> None:
        if self.loop is None or not self.clients:
            return
        clean = _strip(msg)
        try:
            asyncio.run_coroutine_threadsafe(self._send_all(clean), self.loop)
        except RuntimeError:
            pass

    async def _send_all(self, msg: dict[str, Any]) -> None:
        data = json.dumps(msg, ensure_ascii=False)
        dead = []
        for ws in list(self.clients):
            try:
                await asyncio.wait_for(ws.send_text(data), timeout=5)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


def _strip(v: Any) -> Any:
    """ไม่ส่งข้อมูลภายใน (คีย์ที่ขึ้นต้นด้วย _ และข้อมูล bytes)"""
    if isinstance(v, dict):
        return {k: _strip(x) for k, x in v.items() if not k.startswith("_") and not isinstance(x, (bytes, bytearray))}
    if isinstance(v, list):
        return [_strip(x) for x in v]
    return v
