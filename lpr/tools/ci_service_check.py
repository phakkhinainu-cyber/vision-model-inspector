"""ตรวจโปรแกรมที่ติดตั้งแล้ว (ใช้ใน CI): รอ service ตอบ, ตั้งค่าครั้งแรก, เพิ่มกล้องจำลอง, รอเหตุการณ์, ส่งออก PDF

python tools/ci_service_check.py OUT.json [--url http://127.0.0.1:8765] [--wait 180]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--wait", type=float, default=180)
    a = ap.parse_args()
    res: dict = {"ok": False, "steps": []}
    c = httpx.Client(base_url=a.url, headers={"X-LPR": "1"}, timeout=30)
    t0 = time.time()
    try:
        while True:
            try:
                h = c.get("/api/health").json()
                res["health"] = h
                break
            except Exception:  # noqa: BLE001
                if time.time() - t0 > a.wait:
                    raise RuntimeError("service ไม่ตอบภายในเวลา")
                time.sleep(2)
        res["steps"].append(f"health after {time.time() - t0:.0f}s")
        st = c.get("/api/auth/status").json()
        if st["setup_required"]:
            c.post("/api/auth/setup", json={"username": "admin", "password": "ci-admin-1", "house_name": "CI"}).raise_for_status()
        else:
            c.post("/api/auth/login", json={"username": "admin", "password": "ci-admin-1"}).raise_for_status()
        sysst = c.get("/api/system/status").json()
        res["system"] = {k: sysst.get(k) for k in ("home", "credentials", "providers", "models", "demo_video", "version")}
        r = c.post("/api/cameras", json={"name": "CI demo", "rtsp_main": sysst["demo_video"], "role": "สองทาง",
                                         "line_coords": [[0.05, 0.6], [0.95, 0.6]]})
        r.raise_for_status()
        cam_id = r.json()["id"]
        t1 = time.time()
        events: list = []
        while time.time() - t1 < a.wait:
            time.sleep(5)
            events = c.get("/api/events").json()["items"]
            cam = c.get("/api/cameras").json()["items"][0]["status"]
            res["camera_status"] = cam
            if len(events) >= 4:
                break
        res["events"] = [{"plate": e["plate_display"], "province": e["province"], "direction": e["direction"],
                          "review": e["review_status"], "has_full": e["has_full"], "has_clip": e["has_clip"]} for e in events]
        res["steps"].append(f"{len(events)} events after {time.time() - t1:.0f}s")
        pdf = c.get("/api/export/events.pdf")
        res["pdf_bytes"] = len(pdf.content) if pdf.status_code == 200 else pdf.status_code
        snap = c.get(f"/api/cameras/{cam_id}/snapshot.jpg")
        res["snapshot_bytes"] = len(snap.content) if snap.status_code == 200 else snap.status_code
        res["ok"] = len(events) >= 3 and isinstance(res["pdf_bytes"], int) and res["pdf_bytes"] > 5000
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
