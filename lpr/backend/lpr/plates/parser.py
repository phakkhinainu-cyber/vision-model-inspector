"""แยกวิเคราะห์ป้ายทะเบียนไทยจากข้อความที่ OCR อ่านได้

รูปแบบที่รองรับ:
- รถยนต์/จักรยานยนต์: ^[0-9]?[ก-ฮ]{1,2}\\s?[0-9]{1,4}$  เช่น 1กข 4521, บต 7783, 1กศ 552
- รถสาธารณะ/บรรทุก:  ^[0-9]{2}-[0-9]{4}$              เช่น 70-4518
- อื่นๆ (เช่นป้ายแดงบางแบบ): เก็บตามที่อ่านได้ และให้สถานะ รอตรวจสอบ

plate_norm (ใช้ค้นหา) เก็บเฉพาะตัวเลขและพยัญชนะ ไม่มีช่องว่างหรือขีด เช่น "1กข4521", "704518"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .provinces import clean_thai, match_province

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
CONSONANTS = frozenset("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")

# ตัวที่ OCR สับสนบ่อยเมื่ออยู่ในตำแหน่งตัวเลข
DIGIT_FIX = {
    "O": "0", "o": "0", "D": "0", "Q": "0", "U": "0", "C": "0",
    "I": "1", "l": "1", "|": "1", "i": "1", "!": "1", "J": "1", "j": "1", "L": "1", "/": "1",
    "Z": "2", "z": "2", "S": "5", "s": "5", "B": "8", "G": "6", "b": "6", "T": "7",
    "g": "9", "q": "9", "A": "4",
}
# ตัวละตินที่หน้าตาคล้ายพยัญชนะไทย เมื่ออยู่ในตำแหน่งตัวอักษร
LETTER_FIX = {"n": "ก", "u": "บ", "W": "พ", "w": "พ", "U": "บ"}

CAR_RE = re.compile(r"^([0-9]?)([ก-ฮ]{1,2})([0-9]{1,4})$")
PUBLIC_RE = re.compile(r"^([0-9]{2})-?([0-9]{4})$")
_MARKS = re.compile(r"[ฯะ-ฺเ-๎]")  # สระ วรรณยุกต์ และ ฯ (ป้ายมีแต่พยัญชนะ)
_JUNK = re.compile(r"[\s\.\,\_\:\;\'\"\`\~\*\+\=\(\)\[\]\{\}<>]")
_SINGLE_LINE = re.compile(r"^\s*([0-9๐-๙]?\s*[ก-ฮ]{1,2}\s*[-]?\s*[0-9๐-๙OoIlSBZ]{1,4})\s*(.*)$")


@dataclass
class ParsedPlate:
    raw: str = ""
    norm: str = ""
    display: str = ""
    province: str | None = None
    province_score: float = 0.0
    kind: str = "empty"  # car | public | other | empty
    valid: bool = False
    confidence: float = 0.0
    lines: list[str] = field(default_factory=list)


def format_display(norm: str) -> str:
    """แปลง plate_norm เป็นข้อความแสดงผล เช่น 1กข4521 -> 1กข 4521, 704518 -> 70-4518"""
    m = CAR_RE.match(norm)
    if m:
        return f"{m.group(1)}{m.group(2)} {m.group(3)}"
    if re.fullmatch(r"[0-9]{6}", norm):
        return f"{norm[:2]}-{norm[2:]}"
    return norm


def _fix_digits(s: str) -> str:
    return "".join(DIGIT_FIX.get(c, c) for c in s)


def normalize_plate_text(text: str) -> tuple[str, str, bool]:
    """คืน (plate_norm, kind, valid)"""
    t = (text or "").translate(THAI_DIGITS)
    t = _JUNK.sub("", t)
    t = _MARKS.sub("", t)
    t = re.sub(r"-+", "-", t).strip("-")
    if not t:
        return "", "empty", False
    # รถสาธารณะ/บรรทุก: ตัวเลขล้วน 2-4 หลัก
    if not any(c in CONSONANTS for c in t):
        digits = _fix_digits(t)
        m = PUBLIC_RE.match(digits)
        if m:
            return m.group(1) + m.group(2), "public", True
        only = re.sub(r"[^0-9]", "", digits)
        return only, ("other" if only else "empty"), False
    idx = [i for i, c in enumerate(t) if c in CONSONANTS]
    first, last = idx[0], idx[-1]
    while first > 0 and t[first - 1] in LETTER_FIX and not (first - 1 == 0 and len(idx) >= 2):
        first -= 1
    prefix = re.sub(r"[^0-9]", "", _fix_digits(t[:first]))[-1:]
    letters = "".join(LETTER_FIX.get(c, c) for c in t[first:last + 1])
    letters = "".join(c for c in letters if c in CONSONANTS)
    number = re.sub(r"[^0-9]", "", _fix_digits(t[last + 1:]))[:4]
    norm = f"{prefix}{letters}{number}"
    if CAR_RE.match(norm):
        return norm, "car", True
    return norm, "other", False


def normalize_query(text: str) -> str:
    """ทำให้ข้อความค้นหาอยู่ในรูปเดียวกับ plate_norm (ค้นบางส่วนได้)"""
    t = (text or "").translate(THAI_DIGITS)
    t = _MARKS.sub("", t)
    return re.sub(r"[^0-9ก-ฮ]", "", t)


def parse_plate(lines: list[tuple[str, float]], min_province_score: float = 80.0) -> ParsedPlate:
    """lines = [(ข้อความ, ความมั่นใจ)] เรียงจากบรรทัดบนลงล่าง"""
    items = [(t.strip(), float(c)) for t, c in lines if t and t.strip()]
    out = ParsedPlate(raw=" / ".join(t for t, _ in items), lines=[t for t, _ in items])
    if not items:
        return out
    # หาบรรทัดจังหวัด
    prov_i, prov, prov_score = -1, None, 0.0
    for i, (t, _) in enumerate(items):
        th = clean_thai(t)
        digits = sum(ch.isdigit() for ch in t.translate(THAI_DIGITS))
        if len(th) < 3 or digits > 1:
            continue
        name, score = match_province(t, min_province_score)
        if name and score > prov_score:
            prov_i, prov, prov_score = i, name, score
    plate_items = [it for i, it in enumerate(items) if i != prov_i]
    # อ่านมาเป็นบรรทัดเดียว เช่น "1กข 4521 กรุงเทพมหานคร"
    if prov is None and len(plate_items) == 1:
        m = _SINGLE_LINE.match(plate_items[0][0])
        if m and m.group(2):
            name, score = match_province(m.group(2), min_province_score)
            if name:
                prov, prov_score = name, score
                plate_items = [(m.group(1), plate_items[0][1])]
    # ถ้ายังไม่มีบรรทัดจังหวัด แต่มีบรรทัดไทยล้วนที่ไม่ใช่ป้าย ให้ตัดทิ้ง (เช่นข้อความกรอบป้าย)
    plate_text = "".join(t for t, _ in plate_items)
    norm, kind, valid = normalize_plate_text(plate_text)
    if not valid and len(plate_items) > 1:
        # ลองทีละบรรทัด เผื่อมีบรรทัดขยะ
        for t, _ in plate_items:
            n2, k2, v2 = normalize_plate_text(t)
            if v2:
                norm, kind, valid = n2, k2, v2
                break
    confs = [c for _, c in plate_items] or [0.0]
    out.norm, out.kind, out.valid = norm, kind, valid
    out.display = format_display(norm)
    out.province, out.province_score = prov, prov_score
    out.confidence = sum(confs) / len(confs) if norm else 0.0
    return out
