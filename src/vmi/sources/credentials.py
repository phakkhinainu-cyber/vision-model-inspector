"""IP-camera credentials.

* Passwords are never written in plain text. On Windows they are encrypted
  with DPAPI (CryptProtectData, bound to the current Windows user). On other
  systems the password is not persisted at all and must be typed per session.
* URLs are always logged through ``config.redact``.
"""
from __future__ import annotations

import base64
import sys
from urllib.parse import quote, urlsplit, urlunsplit


def dpapi_available() -> bool:
    return sys.platform == "win32"


def _blob(data: bytes):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf, DATA_BLOB


def protect(secret: str) -> str:
    """Encrypt for the current Windows user. Returns '' when unavailable."""
    if not secret or not dpapi_available():
        return ""
    import ctypes
    blob_in, _keep, DATA_BLOB = _blob(secret.encode("utf-8"))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob_in), "VMI", None, None, None,
                                                  0x1, ctypes.byref(blob_out)):
        return ""
    try:
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return "dpapi:" + base64.b64encode(data).decode()


def unprotect(token: str) -> str:
    if not token or not token.startswith("dpapi:") or not dpapi_available():
        return ""
    import ctypes
    raw = base64.b64decode(token[6:])
    blob_in, _keep, DATA_BLOB = _blob(raw)
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None,
                                                    0x1, ctypes.byref(blob_out)):
        return ""
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def strip_credentials(url: str) -> tuple:
    """Return (url_without_credentials, user, password)."""
    p = urlsplit(url.strip())
    user, pwd = p.username or "", p.password or ""
    host = p.hostname or ""
    if p.port:
        host = f"{host}:{p.port}"
    return urlunsplit((p.scheme, host, p.path, p.query, p.fragment)), user, pwd


def build_url(url: str, user: str, password: str) -> str:
    if not user:
        return url
    p = urlsplit(url)
    host = p.hostname or ""
    if p.port:
        host = f"{host}:{p.port}"
    auth = quote(user, safe="") + (":" + quote(password, safe="") if password else "")
    return urlunsplit((p.scheme, f"{auth}@{host}", p.path, p.query, p.fragment))
