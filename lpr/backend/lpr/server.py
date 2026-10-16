"""เปิด web server (HTTP ในวง LAN + HTTPS แบบ self-signed ถ้าเปิดไว้) และตั้งค่า log แบบหมุนเวียน"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import logging.handlers
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Paths, default_home

log = logging.getLogger("lpr")


def setup_logging(paths: Paths, console: bool = True) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    fh = logging.handlers.RotatingFileHandler(paths.logs / "lpr.log", maxBytes=10 * 1024 * 1024, backupCount=7,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console and sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    for noisy in ("uvicorn.access", "httpx", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def lan_ips() -> list[str]:
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(str(info[4][0]))
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def ensure_selfsigned(paths: Paths) -> tuple[Path, Path]:
    """สร้าง certificate แบบ self-signed สำหรับใช้ในบ้าน (ชื่อเครื่อง + IP ในวง LAN)"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    paths.certs.mkdir(parents=True, exist_ok=True)
    crt, key = paths.certs / "lpr.crt", paths.certs / "lpr.key"
    if crt.exists() and key.exists():
        return crt, key
    k = ec.generate_private_key(ec.SECP256R1())
    host = socket.gethostname()
    sans: list[x509.GeneralName] = [x509.DNSName(host), x509.DNSName("localhost"),
                                    x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    for ip in lan_ips():
        sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"LPR {host}")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650)).add_extension(x509.SubjectAlternativeName(sans), False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(k, hashes.SHA256()))
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    return crt, key


class Server:
    """รัน uvicorn ใน thread แยก (ใช้ได้ทั้งโหมด service และหน้าต่างโปรแกรม)"""

    def __init__(self, home: Path | None = None, start_cameras: bool = True, console: bool = True) -> None:
        self.paths = Paths(home or default_home()).ensure()
        setup_logging(self.paths, console)
        from .context import AppContext

        self.ctx = AppContext(self.paths.home, start_cameras=start_cameras)
        self.port = int(self.ctx.settings.get("port"))
        self.host = "0.0.0.0" if self.ctx.settings.get("bind_lan") else "127.0.0.1"
        self._servers: list = []
        self._thread: threading.Thread | None = None

    def _build(self):  # type: ignore[no-untyped-def]
        import uvicorn

        from .api.app import create_app

        app = create_app(self.ctx)
        servers = [uvicorn.Server(uvicorn.Config(app, host=self.host, port=self.port, log_config=None,
                                                 access_log=False, ws_ping_interval=20, proxy_headers=True,
                                                 forwarded_allow_ips="127.0.0.1"))]
        if self.ctx.settings.get("https_selfsigned"):
            crt, key = ensure_selfsigned(self.paths)
            servers.append(uvicorn.Server(uvicorn.Config(app, host=self.host,
                                                         port=int(self.ctx.settings.get("https_port")),
                                                         ssl_certfile=str(crt), ssl_keyfile=str(key),
                                                         log_config=None, access_log=False, lifespan="off")))
        return servers

    def run(self) -> None:
        """รันจนกว่าจะถูกหยุด (blocking)"""
        self._servers = self._build()
        log.info("LPR บ้าน เปิดที่ http://127.0.0.1:%d  (LAN: %s)  ข้อมูล: %s", self.port,
                 ", ".join(f"http://{ip}:{self.port}" for ip in lan_ips()) if self.host == "0.0.0.0" else "ปิด",
                 self.paths.home)

        async def main() -> None:
            await asyncio.gather(*(s.serve() for s in self._servers))

        asyncio.run(main())

    def start_background(self) -> "Server":
        self._thread = threading.Thread(target=self.run, daemon=True, name="lpr-server")
        self._thread.start()
        return self

    def wait_ready(self, timeout: float = 60) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self._servers and getattr(self._servers[0], "started", False):
                return True
            time.sleep(0.1)
        return False

    def stop(self) -> None:
        for s in self._servers:
            s.should_exit = True
        if self._thread:
            self._thread.join(timeout=15)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
