"""process ของกล้องหนึ่งตัว (แยก process ต่อกล้อง เพื่อไม่ให้กล้องที่ค้างกระทบตัวอื่น)

สื่อสารกับ process หลักผ่าน queue:
  cmd_q    (หลัก -> กล้อง)  stop, preview, snapshot, capture
  out_q    (กล้อง -> หลัก)  status, info, event, clip, snapshot, error
  preview_q (กล้อง -> หลัก) ภาพสด JPEG (เก็บแค่ภาพล่าสุด)
"""
from __future__ import annotations

import logging
import logging.handlers
import queue
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..vision.geometry import parse_points
from .clips import ClipScheduler, RingBuffer
from .pipeline import CameraPipeline, Models, jpeg
from .stream import StreamReader


def _put(q, item: Any) -> None:  # type: ignore[no-untyped-def]
    try:
        q.put_nowait(item)
    except queue.Full:
        pass


def draw_overlay(frame: np.ndarray, pipe: CameraPipeline) -> np.ndarray:
    img = frame.copy()
    h, w = img.shape[:2]
    if len(pipe.roi) >= 3:
        pts = np.array([[x * w, y * h] for x, y in pipe.roi], np.int32)
        cv2.polylines(img, [pts], True, (202, 56, 67), 2)
    if len(pipe.line) == 2:
        (x1, y1), (x2, y2) = pipe.line
        cv2.line(img, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), (12, 65, 194), 3)
    for t in pipe.tracker.tracks:
        x1, y1, x2, y2 = t.box.astype(int)
        cv2.rectangle(img, (x1, y1), (x2, y2), (216, 78, 29) if t.confirmed else (150, 150, 150), 2)
        st = t.data.get("st")
        label = f"#{t.id}"
        if st is not None and st.voter.count:
            r = st.voter.result()
            if r.norm:
                label += f" {r.norm}"
        cv2.putText(img, label, (x1 + 3, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    return img


def worker_main(cam: dict[str, Any], params: dict[str, Any], model_paths: dict[str, str | None],
                dirs: dict[str, str], threads: int, cmd_q, out_q, preview_q, log_q) -> None:  # type: ignore[no-untyped-def]
    root = logging.getLogger()
    root.handlers[:] = [logging.handlers.QueueHandler(log_q)]
    root.setLevel(logging.INFO)
    log = logging.getLogger(f"lpr.camera.{cam.get('id')}")
    cam_id = cam.get("id")
    try:
        models = Models(model_paths, params, threads)
    except Exception as e:  # noqa: BLE001
        log.exception("โหลดโมเดลไม่สำเร็จ")
        _put(out_q, {"type": "status", "camera_id": cam_id, "state": "error", "error": f"โหลดโมเดลไม่สำเร็จ: {e}"})
        return
    _put(out_q, {"type": "info", "camera_id": cam_id, **models.info()})

    clip_on = bool(params.get("clip_enabled", True))
    pre, post = float(params.get("clip_pre_seconds", 3)), float(params.get("clip_post_seconds", 5))
    fps = int(params.get("clip_fps", 10))
    ring = RingBuffer(pre + post + 2, fps=fps) if clip_on else None
    main_url = cam.get("url_main") or ""
    sub_url = cam.get("url_sub") or main_url
    main_reader = StreamReader(main_url, f"cam{cam_id}-main", on_frame=ring.push if ring else None).start()
    sub_reader = main_reader if sub_url == main_url else StreamReader(sub_url, f"cam{cam_id}-sub").start()
    clips = None
    if ring is not None:
        clips = ClipScheduler(ring, Path(dirs["tmp"]), pre, post, fps,
                              on_done=lambda uid, path: _put(out_q, {"type": "clip", "uid": uid, "path": path}))
    collect = Path(dirs["collect"]) if params.get("collect_plates") else None
    pipe = CameraPipeline(cam, params, models, collect)
    preview_until = 0.0
    last_preview = last_status = 0.0
    seq = -1
    events_total = 0
    last_event_ts = None
    try:
        while True:
            stop = False
            while True:
                try:
                    cmd = cmd_q.get_nowait()
                except queue.Empty:
                    break
                c = cmd.get("cmd")
                if c == "stop":
                    stop = True
                elif c == "preview":
                    preview_until = time.time() + 20 if cmd.get("on", True) else 0.0
                elif c == "snapshot":
                    f, _, _ = main_reader.latest()
                    _put(out_q, {"type": "snapshot", "req": cmd.get("req"), "jpeg": jpeg(f) if f is not None else b""})
                elif c == "capture":
                    f, _, _ = main_reader.latest()
                    if f is None:
                        _put(out_q, {"type": "capture_done", "req": cmd.get("req"), "error": "ยังไม่ได้รับภาพจากกล้อง"})
                    else:
                        ev = pipe.capture_now(f, direction=cmd.get("direction"))
                        _put(out_q, ev)
                        if clips is not None:
                            clips.request(ev["uid"], ev["ts"])
                        _put(out_q, {"type": "capture_done", "req": cmd.get("req"), "uid": ev["uid"]})
            if stop:
                break
            frame, ts, s2 = sub_reader.wait_new(seq, timeout=0.5)
            now = time.time()
            if frame is not None and s2 != seq:
                seq = s2
                hi = frame if main_reader is sub_reader else main_reader.latest()[0]
                for ev in pipe.step(frame, hi, ts):
                    _put(out_q, ev)
                    events_total += 1
                    last_event_ts = ev["ts"]
                    if clips is not None:
                        clips.request(ev["uid"], ev["ts"])
                if now < preview_until and now - last_preview >= 0.2:
                    last_preview = now
                    img = draw_overlay(frame, pipe)
                    h, w = img.shape[:2]
                    if w > 960:
                        img = cv2.resize(img, (960, int(h * 960 / w)), interpolation=cv2.INTER_AREA)
                    try:
                        while True:
                            preview_q.get_nowait()
                    except queue.Empty:
                        pass
                    _put(preview_q, (now, jpeg(img, 75)))
            if clips is not None:
                clips.tick()
            if now - last_status >= 2.0:
                last_status = now
                _put(out_q, {
                    "type": "status", "camera_id": cam_id,
                    "state": "online" if sub_reader.connected else "connecting",
                    "error": sub_reader.last_error or main_reader.last_error,
                    "fps": round(sub_reader.fps, 1), "size": list(sub_reader.size), "size_main": list(main_reader.size),
                    "night": pipe.night, "ir": pipe.daynight.ir, "brightness": round(pipe.daynight.brightness, 1),
                    "motion": round(pipe.motion.last_ratio, 4), "tracks": len(pipe.tracker.tracks),
                    "reconnects": sub_reader.reconnects, "events": events_total, "last_event_ts": last_event_ts,
                    "stats": dict(pipe.stats), "ts": now,
                })
    finally:
        main_reader.stop()
        if sub_reader is not main_reader:
            sub_reader.stop()


def camera_dict(row: Any, password: str = "") -> dict[str, Any]:
    """แปลงแถว Camera ในฐานข้อมูลเป็น dict ที่ส่งให้ process กล้องได้ (ใส่ชื่อผู้ใช้/รหัสผ่านใน URL)"""
    def with_cred(url: str) -> str:
        if not url or not row.username or "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        if "@" in rest.split("/", 1)[0]:
            return url
        from urllib.parse import quote

        return f"{scheme}://{quote(row.username, safe='')}:{quote(password, safe='')}@{rest}"

    return {
        "id": row.id, "name": row.name, "role": row.role, "roi_polygon": parse_points(row.roi_polygon),
        "line_coords": parse_points(row.line_coords), "line_direction": row.line_direction,
        "url_main": with_cred(row.rtsp_main), "url_sub": with_cred(row.rtsp_sub) if row.rtsp_sub else "",
    }
