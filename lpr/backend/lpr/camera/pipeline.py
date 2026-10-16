"""ขั้นตอนประมวลผลของกล้องหนึ่งตัว (ไม่ขึ้นกับ process/queue จึงทดสอบและใช้ซ้ำได้)

sub-stream -> ตรวจความเคลื่อนไหวใน ROI -> YOLO ตรวจรถ + ByteTrack -> แต่ละคัน: หาป้ายในกรอบรถ (จาก main-stream)
-> ครอป/ปรับภาพ/OCR -> โหวตหลายเฟรม -> ข้ามเส้นเสมือนหรือ track จบ -> เหตุการณ์ 1 รายการ
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .. import constants as C
from ..plates.vehicle_type import merge_vehicle_type
from ..vision.geometry import crossing, net_side_motion, parse_points, point_in_poly
from ..vision.motion import DayNight, MotionDetector
from ..vision.ocr import create_engine
from ..vision.ocr.textdet import DbTextDetector
from ..vision.plate_detect import PlateDetector
from ..vision.preprocess import sharpness
from ..vision.reader import PlateReader
from ..vision.tracker import ByteTracker, Track
from ..vision.voting import Candidate, PlateVoter
from ..vision.yolo import COCO_VEHICLES, YoloDetector

log = logging.getLogger(__name__)


def jpeg(img: np.ndarray, q: int = 88) -> bytes:
    ok, b = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return b.tobytes() if ok else b""


class Models:
    """โมเดลทั้งหมดที่กล้องหนึ่งตัวใช้"""

    def __init__(self, paths: dict[str, str | None], params: dict[str, Any], threads: int = 0) -> None:
        device = params.get("device", "auto")
        if not paths.get("vehicle"):
            raise RuntimeError("ไม่พบโมเดลตรวจจับรถ (vehicle_yolo11n.onnx)")
        self.vehicle = YoloDetector(Path(paths["vehicle"]), device, threads)  # type: ignore[arg-type]
        self.plate = PlateDetector(Path(paths["plate"]) if paths.get("plate") else None, device, threads)
        rec = Path(paths["ocr_rec"]) if paths.get("ocr_rec") else None
        dic = Path(paths["ocr_dict"]) if paths.get("ocr_dict") else None
        self.ocr = create_engine(params.get("ocr_engine", "auto"), rec, dic, device, threads)
        det = None
        if paths.get("ocr_det"):
            try:
                det = DbTextDetector(Path(paths["ocr_det"]), device, threads)  # type: ignore[arg-type]
            except Exception as e:  # noqa: BLE001
                log.warning("โหลดโมเดลแยกบรรทัดไม่ได้: %s", e)
        self.reader = PlateReader(self.ocr, det, float(params.get("province_min_score", 80)))
        self.device = self.vehicle.provider

    def info(self) -> dict[str, str]:
        return {"ocr": self.ocr.name, "plate_detector": self.plate.kind, "device": self.device}


@dataclass
class TrackState:
    voter: PlateVoter
    emitted: bool = False
    cross_ts: float | None = None
    cross_dir: int = 0
    fallback_full: bytes = b""
    fallback_area: float = 0.0
    start: tuple[float, float] | None = None
    plate_seen: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class CameraPipeline:
    def __init__(self, cam: dict[str, Any], params: dict[str, Any], models: Models,
                 collect_dir: Path | None = None) -> None:
        self.cam = cam
        self.p = params
        self.m = models
        self.roi = parse_points(cam.get("roi_polygon"))
        line = parse_points(cam.get("line_coords"))
        self.line = line if len(line) == 2 else []
        self.role = cam.get("role", C.ROLE_BOTH)
        self.in_sign = 1 if cam.get("line_direction", C.LINE_POS_IN) == C.LINE_POS_IN else -1
        self.motion = MotionDetector(self.roi, float(params.get("motion_threshold", 0.004)))
        self.daynight = DayNight(int(params.get("night_brightness", 70)))
        self.tracker = ByteTracker(timeout_s=float(params.get("track_timeout_seconds", 2.5)))
        self.motion_until = 0.0
        self.last_detect = 0.0
        self.last_daynight = 0.0
        self.collect_dir = collect_dir if params.get("collect_plates") else None
        self.stats = {"detect_runs": 0, "ocr_runs": 0, "events": 0}

    # ------------------------------------------------------------------ helpers
    @property
    def night(self) -> bool:
        return self.daynight.night

    def _direction(self, sign: int) -> str:
        if self.role == C.ROLE_IN:
            return C.DIR_IN
        if self.role == C.ROLE_OUT:
            return C.DIR_OUT
        if sign == 0:
            return C.DIR_IN
        return C.DIR_IN if sign == self.in_sign else C.DIR_OUT

    @staticmethod
    def _norm_center(t: Track, w: int, h: int, i: int = -1) -> tuple[float, float]:
        _, cx, cy = t.centers[i]
        return cx / w, cy / h

    # ------------------------------------------------------------------ main step
    def step(self, sub: np.ndarray, hi: np.ndarray | None, ts: float | None = None) -> list[dict[str, Any]]:
        ts = time.time() if ts is None else ts
        hi = sub if hi is None else hi
        if ts - self.last_daynight > 1.0:
            self.daynight.update(sub, ts)
            self.last_daynight = ts
        if self.motion.update(sub):
            self.motion_until = ts + float(self.p.get("motion_hold_seconds", 3.0))
        events: list[dict[str, Any]] = []
        if ts >= self.motion_until and not self.tracker.tracks:
            return events
        if ts - self.last_detect < 1.0 / float(self.p.get("detect_fps", 8.0)):
            return events
        self.last_detect = ts
        self.stats["detect_runs"] += 1
        sh, sw = sub.shape[:2]
        conf = float(self.p.get("vehicle_conf", 0.35)) * (0.85 if self.night else 1.0)
        self.tracker.high = conf  # ByteTrack: กล่องที่มั่นใจต่ำกว่านี้ใช้ต่อ track เดิมเท่านั้น
        dets = self.m.vehicle.detect(sub, conf=min(self.tracker.low, conf), classes=set(COCO_VEHICLES))
        dets = [d for d in dets if point_in_poly(self.roi, (d.x1 + d.x2) / 2 / sw, (d.y1 + d.y2) / 2 / sh)]
        tracks, ended = self.tracker.update(dets, ts)
        hh, hw = hi.shape[:2]
        sx, sy = hw / sw, hh / sh
        for t in tracks:
            st: TrackState = t.data.setdefault("st", TrackState(PlateVoter(int(self.p.get("vote_max_frames", 15)))))
            if st.start is None:
                st.start = self._norm_center(t, sw, sh, 0)
            if not t.updated:
                continue
            self._read_plate(t, st, hi, sx, sy, ts)
            if self.line and len(t.centers) >= 2 and st.cross_dir == 0:
                c = crossing(self.line, self._norm_center(t, sw, sh, -2), self._norm_center(t, sw, sh, -1))
                if c:
                    st.cross_dir, st.cross_ts = c, ts
            if st.cross_ts is not None and not st.emitted:
                waited = ts - st.cross_ts
                if st.voter.count >= int(self.p.get("vote_min_frames", 5)) or \
                        waited >= float(self.p.get("crossing_wait_seconds", 1.0)):
                    events.append(self._emit(t, st, sw, sh))
        for t in ended:
            st = t.data.get("st")
            if st is not None and not st.emitted and self._qualifies(t, st, sw, sh):
                events.append(self._emit(t, st, sw, sh))
        return events

    def flush(self, sub_size: tuple[int, int]) -> list[dict[str, Any]]:
        """จบทุก track (เช่นตอนปิดกล้อง หรือจบไฟล์วิดีโอ)"""
        sw, sh = sub_size
        out = []
        for t in self.tracker.flush():
            st = t.data.get("st")
            if st is not None and not st.emitted and self._qualifies(t, st, sw, sh):
                out.append(self._emit(t, st, sw, sh))
        return out

    def _qualifies(self, t: Track, st: TrackState, sw: int, sh: int) -> bool:
        if not self.p.get("emit_on_track_end", True) and self.line:
            return False
        if t.hits < 3:
            return False
        if st.plate_seen:
            return True
        end = self._norm_center(t, sw, sh, -1)
        start = st.start or end
        moved = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
        return moved >= float(self.p.get("min_track_movement", 0.04))

    def _read_plate(self, t: Track, st: TrackState, hi: np.ndarray, sx: float, sy: float, ts: float) -> None:
        hh, hw = hi.shape[:2]
        x1, y1, x2, y2 = t.box * np.array([sx, sy, sx, sy])
        px, py = (x2 - x1) * 0.04, (y2 - y1) * 0.04
        x1, y1 = int(max(0, x1 - px)), int(max(0, y1 - py))
        x2, y2 = int(min(hw, x2 + px)), int(min(hh, y2 + py))
        crop = hi[y1:y2, x1:x2]
        if crop.size == 0:
            return
        area = float((x2 - x1) * (y2 - y1))
        if not st.plate_seen and area > st.fallback_area:
            st.fallback_area = area
            st.fallback_full = jpeg(hi)
        pb = self.m.plate.detect(crop, conf=float(self.p.get("plate_conf", 0.3)))
        if pb is None:
            return
        plate = pb.crop(crop)
        if plate.size == 0 or plate.shape[0] < 8 or plate.shape[1] < 16:
            return
        st.plate_seen += 1
        sharp = sharpness(plate) * min(1.0, plate.shape[1] / 150.0)
        if st.voter.count >= st.voter.max_frames and sharp <= st.voter.min_sharpness():
            return
        self.stats["ocr_runs"] += 1
        pr = self.m.reader.read(plate, night=self.night, ir_frame=self.daynight.ir)
        p = pr.parsed
        cand = Candidate(p.norm, p.display, p.raw, p.province, p.province_score, p.confidence, sharp, p.valid,
                         p.kind, pr.bg, pr.fg, pr.n_lines, ts)
        if st.voter.add(cand):
            cand.extra["plate_jpg"] = jpeg(plate, 92)
            cand.extra["full_jpg"] = jpeg(hi)
            cand.extra["box"] = [x1 + pb.x1, y1 + pb.y1, x1 + pb.x2, y1 + pb.y2]
        if self.collect_dir is not None:
            self._collect(plate, p.display or "unread", p.province or "")

    def _collect(self, plate: np.ndarray, label: str, province: str) -> None:
        try:
            d = self.collect_dir / time.strftime("%Y%m%d")  # type: ignore[operator]
            d.mkdir(parents=True, exist_ok=True)
            name = f"{int(time.time() * 1000)}_{label.replace(' ', '_')}.jpg"
            cv2.imwrite(str(d / name), plate)
            with open(d / "labels.tsv", "a", encoding="utf-8") as f:
                f.write(f"{name}\t{label}\t{province}\n")
        except Exception:  # noqa: BLE001
            log.exception("collect plate failed")

    def _emit(self, t: Track, st: TrackState, sw: int, sh: int, source: str = C.SOURCE_AUTO) -> dict[str, Any]:
        st.emitted = True
        self.stats["events"] += 1
        res = st.voter.result()
        sign = st.cross_dir
        if sign == 0 and len(t.centers) >= 2:
            sign = net_side_motion(self.line, st.start or self._norm_center(t, sw, sh, 0),
                                   self._norm_center(t, sw, sh, -1))
        yolo_cls = COCO_VEHICLES.get(t.cls)
        best = res.best
        ts = st.cross_ts or (best.ts if best else t.last_ts)
        return {
            "type": "event", "uid": uuid.uuid4().hex, "camera_id": self.cam.get("id"), "ts": ts,
            "direction": self._direction(sign), "plate_norm": res.norm, "plate_display": res.display,
            "plate_raw": res.raw, "province": res.province or "", "confidence": res.confidence,
            "valid": res.valid, "kind": res.kind, "plate_bg": res.bg, "plate_fg": res.fg,
            "n_lines": res.n_lines, "yolo_class": yolo_cls or "",
            "vehicle_type": merge_vehicle_type(yolo_cls, res.bg, res.fg, res.kind, res.n_lines),
            "frames": res.frames, "night": self.night, "source": source,
            "full_jpg": (best.extra.get("full_jpg") if best and best.extra.get("full_jpg") else st.fallback_full),
            "plate_jpg": best.extra.get("plate_jpg", b"") if best else b"",
        }

    # ------------------------------------------------------------------ manual
    def capture_now(self, hi: np.ndarray, ts: float | None = None, direction: str | None = None) -> dict[str, Any]:
        """ปุ่ม จับภาพเดี๋ยวนี้: วิเคราะห์ภาพปัจจุบันทันที (รถคันที่ใหญ่ที่สุด)"""
        ts = time.time() if ts is None else ts
        dets = self.m.vehicle.detect(hi, conf=0.25, classes=set(COCO_VEHICLES))
        dets.sort(key=lambda d: d.w * d.h, reverse=True)
        t = Track(0, np.array([0, 0, hi.shape[1] - 1, hi.shape[0] - 1], np.float32), 1.0, ts, ts)
        if dets:
            d = dets[0]
            t.box = d.box
            t.classes[d.cls] += 1
        t.centers.append((ts, *t.center))
        st = TrackState(PlateVoter(3))
        self._read_plate(t, st, hi, 1.0, 1.0, ts)
        if not st.fallback_full:
            st.fallback_full = jpeg(hi)
        ev = self._emit(t, st, hi.shape[1], hi.shape[0], source=C.SOURCE_CAPTURE)
        ev["ts"] = ts
        if direction:
            ev["direction"] = direction
        return ev
