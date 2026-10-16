"""โหวตผลจากหลายเฟรม: เก็บเฟรมที่ป้ายคมที่สุด 5–15 เฟรม เลือกผลที่ซ้ำบ่อยและความมั่นใจสูงสุด
ให้ได้ผลเดียวต่อรถหนึ่งคัน"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Candidate:
    norm: str
    display: str
    raw: str
    province: str | None
    province_score: float
    conf: float
    sharp: float
    valid: bool
    kind: str
    bg: str
    fg: str
    n_lines: int
    ts: float
    extra: dict[str, Any] = field(default_factory=dict)  # ภาพ (jpeg bytes) ของเฟรมนี้


@dataclass
class VoteResult:
    norm: str
    display: str
    raw: str
    province: str | None
    confidence: float
    valid: bool
    kind: str
    bg: str
    fg: str
    n_lines: int
    frames: int
    best: Candidate | None
    alternatives: list[dict[str, Any]] = field(default_factory=list)


class PlateVoter:
    def __init__(self, max_frames: int = 15) -> None:
        self.max_frames = max_frames
        self.cands: list[Candidate] = []
        self.seen = 0

    def add(self, c: Candidate) -> bool:
        """คืน True ถ้าเฟรมนี้ถูกเก็บไว้ (คมพอที่จะติดอันดับ)"""
        self.seen += 1
        if len(self.cands) < self.max_frames:
            self.cands.append(c)
            return True
        worst = min(range(len(self.cands)), key=lambda i: self.cands[i].sharp)
        if c.sharp > self.cands[worst].sharp:
            self.cands[worst] = c
            return True
        return False

    def min_sharpness(self) -> float:
        return min((c.sharp for c in self.cands), default=0.0)

    @property
    def count(self) -> int:
        return len(self.cands)

    def result(self) -> VoteResult:
        read = [c for c in self.cands if c.norm]
        if not read:
            best = max(self.cands, key=lambda c: c.sharp, default=None)
            return VoteResult("", "", "", None, 0.0, False, "empty", best.bg if best else "unknown",
                              best.fg if best else "unknown", best.n_lines if best else 0, len(self.cands), best)
        groups: dict[str, list[Candidate]] = defaultdict(list)
        for c in read:
            groups[c.norm].append(c)

        max_sharp = max((c.sharp for c in read), default=1.0) or 1.0

        def score(items: list[Candidate]) -> float:
            # ความถี่ × ความมั่นใจ × ความคม (ป้ายที่ใกล้/คมกว่าเชื่อถือได้มากกว่า, รูปแบบถูกต้องได้น้ำหนักเพิ่ม)
            return sum(c.conf * (1.0 if c.valid else 0.6) * (0.4 + 0.6 * (c.sharp / max_sharp) ** 0.5)
                       for c in items)

        ranked = sorted(groups.items(), key=lambda kv: score(kv[1]), reverse=True)
        norm, items = ranked[0]
        agreement = len(items) / len(read)
        mean_conf = sum(c.conf for c in items) / len(items)
        confidence = mean_conf * (0.6 + 0.4 * agreement)
        total = sum(score(v) for _, v in ranked) or 1.0
        if len(ranked) > 1:
            # ผลอันดับ 2 ใกล้เคียงอันดับ 1 = ไม่แน่ใจ -> ลดความมั่นใจ (เข้าคิว รอตรวจสอบ)
            confidence *= 1.0 - 0.5 * score(ranked[1][1]) / score(items)
        alternatives = [{"plate_norm": n, "display": v[0].display, "share": round(score(v) / total, 3)}
                        for n, v in ranked[:3]]
        # จังหวัด: โหวตแยก ถ่วงด้วยคะแนนจับคู่
        prov_votes: dict[str, float] = defaultdict(float)
        for c in read:
            if c.province:
                prov_votes[c.province] += c.province_score * (1.5 if c.norm == norm else 1.0)
        province = max(prov_votes.items(), key=lambda kv: kv[1])[0] if prov_votes else None
        best = max(items, key=lambda c: (c.sharp * (0.5 + c.conf)))
        colors = [c for c in self.cands if c.bg != "unknown"]
        bg = max(set(c.bg for c in colors), key=lambda b: sum(1 for c in colors if c.bg == b)) if colors else "unknown"
        fgs = [c.fg for c in colors if c.bg == bg]
        fg = max(set(fgs), key=fgs.count) if fgs else "unknown"
        return VoteResult(norm, best.display, best.raw, province, round(confidence, 4), best.valid, best.kind,
                          bg, fg, best.n_lines, len(self.cands), best, alternatives)
