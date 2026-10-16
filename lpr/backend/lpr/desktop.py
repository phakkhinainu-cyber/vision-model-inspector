"""หน้าต่างโปรแกรมบนคอม (pywebview) + ไอคอนที่ system tray

- ถ้า Windows service ทำงานอยู่ หน้าต่างแค่เปิด UI (ปิดหน้าต่างแล้วระบบยังจับภาพต่อ)
- ถ้าไม่มี service (เช่นรันแบบพกพา หรือบน macOS/Linux) จะเปิดระบบในตัว และย่อไปที่ tray เมื่อปิดหน้าต่าง
- เครื่องที่ไม่มี WebView2/pywebview จะเปิดผ่านเบราว์เซอร์แทน
"""
from __future__ import annotations

import logging
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import APP_NAME
from .config import Paths, default_home, resources_dir

log = logging.getLogger(__name__)


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _port(home: Path) -> int:
    from .db.session import Database
    from .settings import SettingsStore

    try:
        return int(SettingsStore(Database(Paths(home).ensure().db)).get("port"))
    except Exception:  # noqa: BLE001
        return 8765


def _tray(url: str, on_show, on_quit, embedded: bool):  # type: ignore[no-untyped-def]
    try:
        import pystray
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    img = Image.open(resources_dir() / "icon.png")
    items = [pystray.MenuItem("เปิดหน้าต่าง", lambda: on_show(), default=True),
             pystray.MenuItem("เปิดในเบราว์เซอร์", lambda: webbrowser.open(url))]
    items.append(pystray.MenuItem("ออกจากโปรแกรม (หยุดจับภาพ)" if embedded else "ปิดหน้าต่าง", lambda: on_quit()))
    icon = pystray.Icon("lpr", img, APP_NAME, pystray.Menu(*items))
    try:
        icon.run_detached()
    except Exception:  # noqa: BLE001
        threading.Thread(target=icon.run, daemon=True).start()
    return icon


def run_desktop(home: Path | None = None, browser: bool = False, start_cameras: bool = True) -> int:
    home = home or default_home()
    url = f"http://127.0.0.1:{_port(home)}"
    server = None
    if not _healthy(url):
        from .server import Server

        server = Server(home, start_cameras=start_cameras, console=False).start_background()
        if not server.wait_ready(90):
            log.error("เปิดระบบไม่สำเร็จ ดู log ที่ %s", Paths(home).logs)
        url = server.url
    embedded = server is not None
    quit_ev = threading.Event()

    try:
        if browser:
            raise RuntimeError("browser mode")
        import webview  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        webbrowser.open(url)
        icon = _tray(url, lambda: webbrowser.open(url), quit_ev.set, embedded)
        if embedded:
            try:
                while not quit_ev.wait(1):
                    pass
            except KeyboardInterrupt:
                pass
            server.stop()  # type: ignore[union-attr]
        if icon is not None:
            icon.stop()
        return 0

    win = webview.create_window(f"สมุดบันทึกเข้า-ออก · {APP_NAME}", url, width=1440, height=900,
                                min_size=(980, 640), background_color="#EEF1F7")

    def on_closing() -> bool:
        if embedded and not quit_ev.is_set():
            win.hide()  # ย่อไปที่ tray ระบบยังจับภาพต่อ
            return False
        return True

    def do_quit() -> None:
        quit_ev.set()
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            pass

    try:
        win.events.closing += on_closing
    except Exception:  # noqa: BLE001
        pass
    icon = _tray(url, lambda: (win.show(), win.restore()), do_quit, embedded)
    try:
        import os

        kw = {"gui": "edgechromium"} if os.name == "nt" else {}  # Windows 10/11 มี WebView2 อยู่แล้ว
        webview.start(private_mode=False, storage_path=str(Paths(home).data / "webview"), **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("เปิดหน้าต่างไม่ได้ (%s) ใช้เบราว์เซอร์แทน", e)
        webbrowser.open(url)
        while embedded and not quit_ev.wait(1):
            pass
    if icon is not None:
        icon.stop()
    if server is not None:
        server.stop()
    time.sleep(0.2)
    return 0
