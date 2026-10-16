"""ทดสอบ API ทั้งระบบ (ไม่เปิดกล้องจริง)"""
import io
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from lpr import constants as C
from lpr.api.app import create_app
from lpr.context import AppContext

H = {"X-LPR": "1"}


@pytest.fixture()
def env(tmp_path):
    ctx = AppContext(tmp_path / "home", start_cameras=False)
    app = create_app(ctx, manage_lifecycle=False)
    with TestClient(app) as c:
        yield ctx, c
    ctx.stop()


def setup_admin(c):
    r = c.post("/api/auth/setup", json={"username": "admin", "password": "secret123", "house_name": "บ้านทดสอบ"},
               headers=H)
    assert r.status_code == 200, r.text


def ingest(ctx, plate="1กข4521", province="กรุงเทพมหานคร", direction=C.DIR_IN, ts=None, conf=0.95, cam=None,
           valid=True, bg="white"):
    return ctx.events.ingest({"uid": uuid.uuid4().hex, "ts": ts or time.time(), "camera_id": cam,
                              "direction": direction, "plate_norm": plate, "plate_raw": plate, "province": province,
                              "confidence": conf, "valid": valid, "plate_bg": bg, "plate_fg": "black",
                              "vehicle_type": C.VT_SEDAN, "full_jpg": _jpg(), "plate_jpg": _jpg()})


def _jpg():
    import cv2
    import numpy as np

    return cv2.imencode(".jpg", np.full((60, 120, 3), 200, np.uint8))[1].tobytes()


def test_setup_and_login_flow(env):
    ctx, c = env
    assert c.get("/api/auth/status").json()["setup_required"] is True
    assert c.get("/api/events").status_code == 401
    setup_admin(c)
    assert c.get("/api/auth/status").json()["house_name"] == "บ้านทดสอบ"
    assert c.post("/api/auth/setup", json={"username": "x", "password": "secret123"}, headers=H).status_code == 409
    assert c.get("/api/auth/me").json()["role"] == "admin"
    c.post("/api/auth/logout", headers=H)
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"username": "admin", "password": "bad"}, headers=H).status_code == 401
    assert c.post("/api/auth/login", json={"username": "ADMIN", "password": "secret123"}, headers=H).status_code == 200


def test_csrf_header_required(env):
    _, c = env
    assert c.post("/api/auth/setup", json={"username": "a", "password": "secret123"}).status_code == 403


def test_login_rate_limit(env):
    ctx, c = env
    setup_admin(c)
    c.post("/api/auth/logout", headers=H)
    for _ in range(5):
        c.post("/api/auth/login", json={"username": "admin", "password": "nope"}, headers=H)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "secret123"}, headers=H)
    assert r.status_code == 429


def test_events_dedup_visits_and_edit(env):
    ctx, c = env
    setup_admin(c)
    t = time.time() - 3600
    e1 = ingest(ctx, ts=t)
    assert ingest(ctx, ts=t + 10) is None  # ซ้ำภายใน 60 วินาที
    e2 = ingest(ctx, direction=C.DIR_OUT, ts=t + 1800)
    unread = ingest(ctx, plate="", province="", ts=t + 100)
    low = ingest(ctx, plate="9กก9999", conf=0.5, ts=t + 200)
    assert e1["review_status"] == C.REVIEW_OK and unread["review_status"] == C.REVIEW_UNREAD
    assert low["review_status"] == C.REVIEW_PENDING
    items = c.get("/api/events").json()["items"]
    assert [i["id"] for i in items] == [e2["id"], low["id"], unread["id"], e1["id"]]
    f = c.get("/api/events/facets").json()
    assert f["total"] == 4 and f["direction"] == {C.DIR_IN: 3, C.DIR_OUT: 1}
    assert c.get("/api/events", params={"q": "4521"}).json()["items"][0]["plate_norm"] == "1กข4521"
    assert len(c.get("/api/events", params={"direction": C.DIR_OUT}).json()["items"]) == 1
    d = c.get(f"/api/events/{e2['id']}").json()
    assert d["vehicle"]["visits_today"] or d["vehicle"]["stats_30d"]["entries"] == 1
    assert d["vehicle"]["stats_30d"] == {**d["vehicle"]["stats_30d"], "entries": 1, "exits": 1, "visits": 1}
    assert c.get(f"/api/events/{e1['id']}/media/full").headers["content-type"] == "image/jpeg"
    assert c.get(f"/api/events/{e1['id']}/media/clip").status_code == 404
    # แก้ไขทะเบียนที่อ่านผิด
    r = c.patch(f"/api/events/{low['id']}", json={"plate": "9กก 9998", "province": "เชียงใหม"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["plate_norm"] == "9กก9998" and r.json()["province"] == "เชียงใหม่"
    assert r.json()["review_status"] == C.REVIEW_EDITED and r.json()["original_plate"].startswith("9กก 9999")
    q = c.get("/api/review").json()
    assert [i["id"] for i in q["items"]] == [unread["id"]]
    audit = c.get("/api/audit").json()["items"]
    assert any(a["action"] == "แก้ไขเหตุการณ์" for a in audit)


def test_pagination(env):
    ctx, c = env
    setup_admin(c)
    t = time.time() - 5000
    for i in range(7):
        ingest(ctx, plate=f"กข{1000 + i}", ts=t + i * 100)
    r1 = c.get("/api/events", params={"limit": 3}).json()
    r2 = c.get("/api/events", params={"limit": 3, "cursor": r1["next_cursor"]}).json()
    r3 = c.get("/api/events", params={"limit": 3, "cursor": r2["next_cursor"]}).json()
    ids = [i["id"] for i in r1["items"] + r2["items"] + r3["items"]]
    assert len(ids) == 7 and len(set(ids)) == 7 and r3["next_cursor"] is None


def test_exports(env):
    ctx, c = env
    setup_admin(c)
    ingest(ctx)
    ingest(ctx, plate="704518", province="ชลบุรี", direction=C.DIR_OUT)
    r = c.get("/api/export/events.csv")
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf") and "1กข 4521" in r.content.decode("utf-8-sig")
    r = c.get("/api/export/events.xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    r = c.get("/api/export/events.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 5000


def test_vehicles_and_import_export(env):
    ctx, c = env
    setup_admin(c)
    ev = ingest(ctx)
    r = c.post(f"/api/vehicles/from-event/{ev['id']}", json={"status": C.VS_MEMBER, "owner_name": "สมชาย",
                                                              "house_no": "99/1"}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == C.VS_MEMBER
    assert c.get(f"/api/events/{ev['id']}").json()["event"]["owner_name"] == "สมชาย"
    r = c.post("/api/vehicles", json={"plate": "บต 7783", "province": "เชียงใหม่", "status": C.VS_WATCH}, headers=H)
    assert r.status_code == 200
    assert c.post("/api/vehicles", json={"plate": "บต7783", "province": "เชียงใหม่"}, headers=H).status_code == 409
    lst = c.get("/api/vehicles").json()
    assert lst["total"] == 2 and lst["counts"][C.VS_WATCH] == 1
    x = c.get("/api/vehicles-export.xlsx")
    assert x.status_code == 200
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["ทะเบียน", "จังหวัด", "สถานะ", "เจ้าของ"])
    ws.append(["5กก 555", "ภูเก็ต", "ผู้มาเยือน", "แขก"])
    ws.append(["", "", "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    r = c.post("/api/vehicles-import", files={"file": ("v.xlsx", buf.getvalue())}, headers=H)
    assert r.status_code == 200 and r.json()["added"] == 1, r.text
    # รถเฝ้าระวังเข้ามา -> แจ้งเตือน (ตรวจว่าเรียก notifier)
    calls = []
    ctx.events.notify = lambda **kw: calls.append(kw)
    ingest(ctx, plate="บต7783", province="เชียงใหม่")
    assert calls and calls[0]["kind"] == "watch"


def test_inside_and_reports(env):
    ctx, c = env
    setup_admin(c)
    now = time.time()
    ingest(ctx, plate="กข1", ts=now - 7200)
    ingest(ctx, plate="กข2", ts=now - 3600)
    ingest(ctx, plate="กข2", direction=C.DIR_OUT, ts=now - 600)
    ins = c.get("/api/visits/inside").json()
    assert [i["vehicle"]["plate_norm"] for i in ins["inside"]] == ["กข1"]
    s = c.get("/api/reports/summary").json()
    assert s["total"] >= 1 and len(s["hours"]) == 24
    ls = c.get("/api/reports/long-stay", params={"hours": 1}).json()
    assert {i["vehicle"]["plate_norm"] for i in ls["items"]} == {"กข1"}


def test_settings_users_and_permissions(env):
    ctx, c = env
    setup_admin(c)
    sch = c.get("/api/settings").json()["items"]
    assert any(i["key"] == "dedup_seconds" for i in sch)
    assert c.put("/api/settings", json={"dedup_seconds": 30}, headers=H).json()["changed"] == ["dedup_seconds"]
    assert ctx.settings.get("dedup_seconds") == 30
    assert c.put("/api/settings", json={"review_threshold": 5}, headers=H).status_code == 400
    r = c.put("/api/settings", json={"port": 9000}, headers=H).json()
    assert "port" in r["restart_required"]
    r = c.put("/api/settings", json={"telegram_token": "abc"}, headers=H)
    tok = next(i for i in c.get("/api/settings").json()["items"] if i["key"] == "telegram_token")
    assert tok["value"] == "" and tok["has_value"] is True
    assert c.post("/api/users", json={"username": "viewer1", "password": "viewpass", "role": "viewer"},
                  headers=H).status_code == 200
    c.post("/api/auth/logout", headers=H)
    c.post("/api/auth/login", json={"username": "viewer1", "password": "viewpass"}, headers=H)
    ev = ingest(ctx)
    assert c.get("/api/events").status_code == 200
    assert c.patch(f"/api/events/{ev['id']}", json={"plate": "x"}, headers=H).status_code == 403
    assert c.put("/api/settings", json={"dedup_seconds": 10}, headers=H).status_code == 403
    assert c.get("/api/users").status_code == 403


def test_cameras_crud_and_test_connection(env, tmp_path):
    ctx, c = env
    setup_admin(c)
    import cv2
    import numpy as np

    img = tmp_path / "cam.jpg"
    cv2.imwrite(str(img), np.full((240, 320, 3), 128, np.uint8))
    r = c.post("/api/cameras", json={"name": "CAM 1 ประตูหน้า", "rtsp_main": "rtsp://admin:p%40ss@192.168.1.20:554/s1",
                                     "role": C.ROLE_IN}, headers=H)
    assert r.status_code == 200, r.text
    cam = r.json()
    assert cam["rtsp_main"] == "rtsp://192.168.1.20:554/s1" and cam["username"] == "admin"
    assert ctx.creds.get(cam["id"]) == "p@ss"
    r = c.patch(f"/api/cameras/{cam['id']}", json={"roi_polygon": [[0, 0], [1, 0], [1, 1]],
                                                   "line_coords": [[0, 0.5], [1, 0.5]]}, headers=H)
    assert r.json()["line_coords"] == [[0.0, 0.5], [1.0, 0.5]]
    assert c.patch(f"/api/cameras/{cam['id']}", json={"line_coords": [[0, 0]]}, headers=H).status_code == 400
    t = c.post("/api/cameras/test", json={"url": str(img)}, headers=H).json()
    assert t["ok"] and t["width"] == 320 and t["image"].startswith("data:image/jpeg")
    assert c.get("/api/cameras").json()["items"][0]["status"]["state"] == "stopped"
    assert c.delete(f"/api/cameras/{cam['id']}", headers=H).status_code == 200


def test_manual_event_and_backup(env):
    ctx, c = env
    setup_admin(c)
    r = c.post("/api/events/manual", json={"plate": "1กข 4521", "province": "กทม", "direction": C.DIR_OUT},
               headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["province"] == "กรุงเทพมหานคร" and r.json()["source"] == "manual"
    b = c.post("/api/backup/run", headers=H).json()
    assert b["size"] > 0
    assert len(c.get("/api/backup/list").json()["items"]) == 1
    st = c.get("/api/system/status").json()
    assert st["house_name"] == "บ้านทดสอบ" and "disk" in st


def test_websocket_receives_events(env):
    ctx, c = env
    setup_admin(c)
    with c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        ingest(ctx)
        msg = ws.receive_json()
        assert msg["type"] == "event" and msg["event"]["plate_norm"] == "1กข4521"
        assert "_thumb_rel" not in msg["event"]
