"""เก็บรหัสผ่านกล้องแบบเข้ารหัส

Windows: Windows Credential Manager (ผ่าน keyring)
เครื่องที่ไม่มี keyring backend (เช่น Linux แบบไม่มีหน้าจอ): เข้ารหัสด้วย Fernet แล้วเก็บในไฟล์
โดยกุญแจเก็บแยกไว้ในโฟลเดอร์ data (สิทธิ์อ่านเฉพาะเจ้าของ)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)
SERVICE = "LPR-ban-camera"


class CredentialStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._keyring = None
        try:
            import keyring
            from keyring.backends import fail

            kr = keyring.get_keyring()
            usable = not isinstance(kr, fail.Keyring) and float(getattr(kr, "priority", 1)) > 0
            if usable and type(kr).__name__ == "ChainerBackend":
                usable = bool(getattr(kr, "backends", None))
            if usable:
                kr.get_password(SERVICE, "__probe__")
                self._keyring = keyring
        except Exception as e:  # noqa: BLE001
            log.info("ไม่มี keyring ใช้ไฟล์เข้ารหัสแทน (%s)", e)
            self._keyring = None

    @property
    def backend(self) -> str:
        return "Windows Credential Manager" if (self._keyring and os.name == "nt") else (
            "keyring" if self._keyring else "ไฟล์เข้ารหัส")

    # ---- fallback file
    def _fernet(self):  # type: ignore[no-untyped-def]
        from cryptography.fernet import Fernet

        kf = self.data_dir / ".camkey"
        if not kf.exists():
            kf.parent.mkdir(parents=True, exist_ok=True)
            kf.write_bytes(Fernet.generate_key())
            try:
                os.chmod(kf, 0o600)
            except OSError:
                pass
        return Fernet(kf.read_bytes())

    def _file(self) -> Path:
        return self.data_dir / "camera_secrets.json"

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self._file().read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def set(self, camera_id: int, password: str) -> None:
        key = f"camera-{camera_id}"
        if self._keyring is not None:
            try:
                if password:
                    self._keyring.set_password(SERVICE, key, password)
                else:
                    try:
                        self._keyring.delete_password(SERVICE, key)
                    except Exception:  # noqa: BLE001
                        pass
                return
            except Exception as e:  # noqa: BLE001
                log.warning("บันทึกลง keyring ไม่ได้ (%s) ใช้ไฟล์เข้ารหัสแทน", e)
        d = self._load()
        if password:
            d[key] = self._fernet().encrypt(password.encode()).decode()
        else:
            d.pop(key, None)
        self._file().write_text(json.dumps(d), "utf-8")

    def get(self, camera_id: int) -> str:
        key = f"camera-{camera_id}"
        if self._keyring is not None:
            try:
                v = self._keyring.get_password(SERVICE, key)
                if v is not None:
                    return v
            except Exception:  # noqa: BLE001
                pass
        enc = self._load().get(key)
        if not enc:
            return ""
        try:
            return self._fernet().decrypt(enc.encode()).decode()
        except Exception:  # noqa: BLE001
            return ""

    def delete(self, camera_id: int) -> None:
        self.set(camera_id, "")
