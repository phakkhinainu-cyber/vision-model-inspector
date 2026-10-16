"""การจับคู่เหตุการณ์ เข้า-ออก เป็นการเข้าพื้นที่ 1 ครั้ง (visit)

กติกา:
- เข้า: ถ้ายังมี visit ที่เปิดอยู่ (เข้าแล้วยังไม่ออก) ให้ปิดเป็น "ไม่พบการออก" แล้วเปิด visit ใหม่
- ออก: ถ้า visit ล่าสุดยังไม่มีการออก (และเข้าก่อนเวลานี้) ให้จับคู่ คำนวณเวลาที่อยู่
        ไม่เช่นนั้นสร้าง visit ที่มีแต่การออก สถานะ "ไม่พบการเข้า"
- เข้าแล้วไม่ออกเกิน overstay ชั่วโมง ให้ติดสถานะ "ไม่พบการออก" (ถ้าภายหลังออก ยังจับคู่ได้)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .. import constants as C


@dataclass(frozen=True)
class VisitRec:
    entry_event_id: int | None
    exit_event_id: int | None
    entry_ts: float | None
    exit_ts: float | None
    status: str
    id: int | None = None

    @property
    def duration_sec(self) -> float | None:
        if self.entry_ts is None or self.exit_ts is None:
            return None
        return max(0.0, self.exit_ts - self.entry_ts)


def step(last: VisitRec | None, event_id: int, ts: float, direction: str) -> tuple[VisitRec | None, VisitRec | None]:
    """คืน (visit ล่าสุดที่ถูกแก้ไข หรือ None, visit ใหม่ หรือ None)"""
    is_open = last is not None and last.exit_event_id is None and last.entry_event_id is not None
    if direction == C.DIR_IN:
        updated = replace(last, status=C.VISIT_NO_EXIT) if is_open and last and last.status != C.VISIT_NO_EXIT else None
        new = VisitRec(event_id, None, ts, None, C.VISIT_INSIDE)
        return updated, new
    # ออก
    if is_open and last is not None and last.entry_ts is not None and last.entry_ts <= ts:
        return replace(last, exit_event_id=event_id, exit_ts=ts, status=C.VISIT_DONE), None
    return None, VisitRec(None, event_id, None, ts, C.VISIT_NO_ENTRY)


def rebuild(events: Iterable[tuple[int, float, str]], now: float | None = None,
            overstay_sec: float | None = None) -> list[VisitRec]:
    """สร้าง visit ทั้งหมดใหม่จากเหตุการณ์ของรถหนึ่งคัน (id, ts, direction) เรียงตามเวลา"""
    out: list[VisitRec] = []
    for eid, ts, d in sorted(events, key=lambda e: (e[1], e[0])):
        last = out[-1] if out else None
        upd, new = step(last, eid, ts, d)
        if upd is not None:
            out[-1] = upd
        if new is not None:
            out.append(new)
    if now is not None and overstay_sec is not None:
        out = [mark_overstay(v, now, overstay_sec) for v in out]
    return out


def mark_overstay(v: VisitRec, now: float, overstay_sec: float) -> VisitRec:
    if v.status == C.VISIT_INSIDE and v.entry_ts is not None and now - v.entry_ts > overstay_sec:
        return replace(v, status=C.VISIT_NO_EXIT)
    return v


def format_duration_th(sec: float | None) -> str:
    if sec is None:
        return "-"
    m = int(sec // 60)
    h, m = divmod(m, 60)
    if h and m:
        return f"{h} ชม. {m} น."
    if h:
        return f"{h} ชม."
    return f"{m} น."
