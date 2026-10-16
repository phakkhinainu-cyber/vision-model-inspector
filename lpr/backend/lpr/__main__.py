"""จุดเริ่มโปรแกรม

  python -m lpr                 เปิดหน้าต่างโปรแกรม (ถ้ายังไม่มี service ทำงาน จะเปิดระบบในตัวด้วย)
  python -m lpr --server        รันเฉพาะระบบเบื้องหลัง (ใช้กับ Windows service)
  python -m lpr --browser       เปิดผ่านเบราว์เซอร์แทนหน้าต่างโปรแกรม
  python -m lpr --selftest OUT.json [--video demo.mp4]   ทดสอบตัวเองหลังติดตั้ง
  python -m lpr --home D:\\LPR    กำหนดที่เก็บข้อมูล
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    ap = argparse.ArgumentParser(prog="lpr", description="LPR บ้าน — ระบบตรวจป้ายทะเบียนรถ")
    ap.add_argument("--server", action="store_true", help="รันเฉพาะระบบเบื้องหลัง")
    ap.add_argument("--browser", action="store_true", help="เปิดผ่านเบราว์เซอร์")
    ap.add_argument("--home", help="โฟลเดอร์เก็บข้อมูล")
    ap.add_argument("--no-cameras", action="store_true", help="ไม่เปิดกล้อง (ทดสอบหน้าเว็บ)")
    ap.add_argument("--selftest", metavar="OUT_JSON", help="ทดสอบระบบแล้วเขียนผลเป็น JSON")
    ap.add_argument("--video", help="วิดีโอสำหรับ selftest")
    a = ap.parse_args(argv)
    if a.home:
        os.environ["LPR_HOME"] = a.home
    home = Path(a.home) if a.home else None
    if a.selftest:
        from .selftest import run_selftest

        return run_selftest(Path(a.selftest), Path(a.video) if a.video else None, home)
    if a.server:
        from .server import Server

        srv = Server(home, start_cameras=not a.no_cameras, console=sys.stderr is not None)
        srv.run()
        return 0
    from .desktop import run_desktop

    return run_desktop(home, browser=a.browser, start_cameras=not a.no_cameras)


if __name__ == "__main__":
    sys.exit(main())
