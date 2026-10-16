"""การแจ้งเตือน: Web Push (VAPID) เป็นหลัก, Telegram Bot และ LINE Messaging API เป็นตัวเลือก

ไม่ใช้ LINE Notify เพราะปิดบริการแล้วตั้งแต่ 31 มี.ค. 2568
ข้อมูลจะออกนอกเครื่องเฉพาะช่องทางที่ผู้ใช้เปิดเองเท่านั้น
"""
from __future__ import annotations

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from ..db.models import PushSubscription
from ..db.session import Database
from ..settings import SettingsStore

log = logging.getLogger(__name__)


def ensure_vapid(settings: SettingsStore) -> str:
    """สร้างกุญแจ VAPID ครั้งแรก คืน public key (base64url) สำหรับหน้าเว็บ"""
    pub = settings.get("vapid_public_b64")
    if pub and settings.get("vapid_private_pem"):
        return str(pub)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    pub = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    settings.update({"vapid_private_pem": pem, "vapid_public_b64": pub})
    return pub


class Notifier:
    def __init__(self, db: Database, settings: SettingsStore) -> None:
        self.db = db
        self.settings = settings
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notify")
        self.last_errors: dict[str, str] = {}

    def __call__(self, *, title: str, body: str, image: Path | None = None, url: str = "/", tag: str = "",
                 kind: str = "") -> None:
        self.pool.submit(self._send_all, title, body, image, url, tag)

    def _send_all(self, title: str, body: str, image: Path | None, url: str, tag: str) -> dict[str, str]:
        st = self.settings
        results: dict[str, str] = {}
        if st.get("webpush_enabled"):
            results["webpush"] = self._guard("webpush", self.webpush, title, body, url, tag)
        if st.get("telegram_enabled") and st.get("telegram_token") and st.get("telegram_chat_id"):
            results["telegram"] = self._guard("telegram", self.telegram, title, body, image)
        if st.get("line_enabled") and st.get("line_token") and st.get("line_to"):
            results["line"] = self._guard("line", self.line, title, body)
        return results

    def _guard(self, name: str, fn, *a: Any) -> str:  # type: ignore[no-untyped-def]
        try:
            r = fn(*a)
            self.last_errors.pop(name, None)
            return r or "ok"
        except Exception as e:  # noqa: BLE001
            log.warning("ส่งแจ้งเตือน %s ไม่สำเร็จ: %s", name, e)
            self.last_errors[name] = str(e)
            return f"error: {e}"

    # ---------------------------------------------------------------- web push
    def webpush(self, title: str, body: str, url: str, tag: str) -> str:
        from pywebpush import WebPushException, webpush

        ensure_vapid(self.settings)
        pem = str(self.settings.get("vapid_private_pem"))
        with self.db.session() as s:
            subs = list(s.scalars(select(PushSubscription)))
        if not subs:
            return "ยังไม่มีอุปกรณ์ที่สมัครรับแจ้งเตือน"
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False)
        sent, gone = 0, []
        for sub in subs:
            try:
                webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, payload,
                        vapid_private_key=_vapid_key_for_pywebpush(pem),
                        vapid_claims={"sub": "mailto:lpr@localhost"}, ttl=3600, timeout=10)
                sent += 1
            except WebPushException as e:
                code = getattr(e.response, "status_code", 0)
                if code in (404, 410):
                    gone.append(sub.id)
                else:
                    log.warning("web push error %s", e)
        if gone:
            with self.db.session() as s:
                s.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
        return f"ส่งถึง {sent} อุปกรณ์"

    # ---------------------------------------------------------------- telegram
    def telegram(self, title: str, body: str, image: Path | None) -> str:
        import httpx

        token = self.settings.get("telegram_token")
        chat = self.settings.get("telegram_chat_id")
        text = f"<b>{_html(title)}</b>\n{_html(body)}"
        base = f"https://api.telegram.org/bot{token}"
        with httpx.Client(timeout=15) as c:
            if image is not None and image.exists():
                r = c.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": text, "parse_mode": "HTML"},
                           files={"photo": (image.name, image.read_bytes(), "image/jpeg")})
            else:
                r = c.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text, "parse_mode": "HTML"})
        if r.status_code != 200:
            raise RuntimeError(f"Telegram ตอบกลับ {r.status_code}: {r.text[:200]}")
        return "ok"

    # ---------------------------------------------------------------- LINE
    def line(self, title: str, body: str) -> str:
        import httpx

        r = httpx.post("https://api.line.me/v2/bot/message/push", timeout=15,
                       headers={"Authorization": f"Bearer {self.settings.get('line_token')}"},
                       json={"to": self.settings.get("line_to"),
                             "messages": [{"type": "text", "text": f"{title}\n{body}"[:4900]}]})
        if r.status_code != 200:
            raise RuntimeError(f"LINE ตอบกลับ {r.status_code}: {r.text[:200]}")
        return "ok"

    def test(self, channel: str) -> str:
        now = time.strftime("%H:%M:%S")
        title, body = "ทดสอบการแจ้งเตือน", f"LPR บ้าน ส่งข้อความทดสอบเวลา {now}"
        fn = {"webpush": lambda: self.webpush(title, body, "/", "test"),
              "telegram": lambda: self.telegram(title, body, None),
              "line": lambda: self.line(title, body)}.get(channel)
        if fn is None:
            raise ValueError("ไม่รู้จักช่องทาง")
        return fn()


def _html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _vapid_key_for_pywebpush(pem: str) -> str:
    """pywebpush รับ private key แบบ base64url ของค่า raw 32 ไบต์"""
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(pem.encode(), password=None)
    raw = key.private_numbers().private_value.to_bytes(32, "big")  # type: ignore[union-attr]
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")
