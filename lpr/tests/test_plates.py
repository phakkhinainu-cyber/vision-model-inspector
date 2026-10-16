"""การแยกวิเคราะห์ป้ายทะเบียนไทย"""
import pytest

from lpr.plates import format_display, normalize_plate_text, normalize_query, parse_plate


@pytest.mark.parametrize("text,norm,kind", [
    ("1กข 4521", "1กข4521", "car"),
    ("บต 7783", "บต7783", "car"),
    ("1กศ 552", "1กศ552", "car"),
    ("๑กข ๔๕๒๑", "1กข4521", "car"),          # เลขไทย
    ("1 กข-4521", "1กข4521", "car"),          # ขีด/ช่องว่างเกิน
    ("กข 45O1", "กข4501", "car"),             # O -> 0 ในส่วนตัวเลข
    ("กข 4I21", "กข4121", "car"),             # I -> 1
    ("lกข 4521", "1กข4521", "car"),           # l -> 1 ในเลขนำหน้า
    ("กข่ 4521", "กข4521", "car"),            # วรรณยุกต์ที่ OCR เติมเกิน
    ("70-4518", "704518", "public"),
    ("70 - 4518", "704518", "public"),
    ("7O-4518", "704518", "public"),
    ("ก 1234", "ก1234", "car"),
])
def test_normalize_valid(text, norm, kind):
    n, k, valid = normalize_plate_text(text)
    assert (n, k, valid) == (norm, kind, True)


@pytest.mark.parametrize("text", ["", "   ", "กขคง 1", "12345", "กข"])
def test_normalize_invalid(text):
    _, _, valid = normalize_plate_text(text)
    assert not valid


def test_display():
    assert format_display("1กข4521") == "1กข 4521"
    assert format_display("704518") == "70-4518"
    assert format_display("กข") == "กข"


def test_query_normalization():
    assert normalize_query("1กข 4521") == "1กข4521"
    assert normalize_query("๔๕๒๑") == "4521"
    assert normalize_query("70-4518") == "704518"


def test_parse_two_lines_car():
    p = parse_plate([("1กข 4521", 0.95), ("กรุงเทพมหานคร", 0.9)])
    assert p.norm == "1กข4521" and p.valid and p.kind == "car"
    assert p.province == "กรุงเทพมหานคร"
    assert p.display == "1กข 4521"
    assert abs(p.confidence - 0.95) < 1e-6
    assert p.raw == "1กข 4521 / กรุงเทพมหานคร"


def test_parse_province_with_ocr_error():
    p = parse_plate([("บต 7783", 0.9), ("เชียงไหม่", 0.7)])
    assert p.province == "เชียงใหม่"


def test_parse_public():
    p = parse_plate([("70-4518", 0.9), ("ชลบุรี", 0.9)])
    assert p.norm == "704518" and p.kind == "public" and p.province == "ชลบุรี"


def test_parse_motorcycle_three_lines():
    # บรรทัดบน = ตัวอักษร, กลาง = จังหวัด, ล่าง = ตัวเลข
    p = parse_plate([("1กศ", 0.9), ("ขอนแก่น", 0.85), ("552", 0.92)])
    assert p.norm == "1กศ552" and p.valid and p.province == "ขอนแก่น"


def test_parse_single_line():
    p = parse_plate([("1กข 4521 กรุงเทพมหานคร", 0.9)])
    assert p.norm == "1กข4521" and p.province == "กรุงเทพมหานคร"


def test_parse_empty_and_unknown_province():
    assert parse_plate([]).kind == "empty"
    p = parse_plate([("กข 1234", 0.9), ("xxxx", 0.2)])
    assert p.valid and p.province is None


def test_parse_red_plate_style_other():
    p = parse_plate([("ก-1234-กข", 0.6)])
    assert not p.valid  # รูปแบบอื่น -> รอตรวจสอบ
