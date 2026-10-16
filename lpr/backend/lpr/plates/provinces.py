"""รายชื่อ 77 จังหวัด และการจับคู่ชื่อจังหวัดที่ OCR อ่านได้ด้วย rapidfuzz"""
from __future__ import annotations

import re
from functools import lru_cache

from rapidfuzz import fuzz, process

PROVINCES: tuple[str, ...] = (
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี",
    "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด",
    "ตาก", "นครนายก", "นครปฐม", "นครพนม", "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี",
    "นราธิวาส", "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี",
    "พระนครศรีอยุธยา", "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์",
    "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง",
    "ระยอง", "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล",
    "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี", "สุโขทัย",
    "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ",
    "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี",
)
assert len(PROVINCES) == 77

# ชื่อย่อ/ชื่อเรียกอื่นที่อาจพบ -> ชื่อเต็ม (เบตงมีป้ายทะเบียนของตัวเอง แต่อยู่ในจังหวัดยะลา)
ALIASES: dict[str, str] = {
    "กรุงเทพ": "กรุงเทพมหานคร",
    "กรุงเทพฯ": "กรุงเทพมหานคร",
    "กทม": "กรุงเทพมหานคร",
    "อยุธยา": "พระนครศรีอยุธยา",
    "เบตง": "เบตง",
}

_NON_THAI = re.compile(r"[^฀-๿]")


def clean_thai(text: str) -> str:
    return _NON_THAI.sub("", text or "")


@lru_cache(maxsize=4096)
def match_province(text: str, min_score: float = 80.0) -> tuple[str | None, float]:
    """คืน (ชื่อจังหวัด, คะแนน 0-100) ถ้าคะแนนต่ำกว่า min_score คืน (None, คะแนนที่ดีที่สุด)"""
    q = clean_thai(text)
    if len(q) < 2:
        return None, 0.0
    choices = list(PROVINCES) + list(ALIASES)
    best = process.extractOne(q, choices, scorer=fuzz.ratio)
    name, score = (best[0], float(best[1])) if best else (None, 0.0)
    # OCR มักอ่านตัวอักษรเกิน/ขาดที่ขอบ ใช้ partial_ratio ช่วยเฉพาะเมื่อเทียบตรงๆ ไม่ผ่าน
    if score < min_score and len(q) >= 4:
        best2 = process.extractOne(q, choices, scorer=fuzz.partial_ratio)
        if best2 and best2[1] * 0.95 > score and abs(len(best2[0]) - len(q)) <= max(3, len(q) // 3):
            name, score = best2[0], float(best2[1]) * 0.95
    if name is None or score < min_score:
        return None, score
    return ALIASES.get(name, name), score
