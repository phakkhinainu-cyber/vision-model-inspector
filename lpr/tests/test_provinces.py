"""การจับคู่จังหวัด 77 จังหวัดด้วย rapidfuzz"""
import pytest

from lpr.plates.provinces import PROVINCES, match_province


def test_count():
    assert len(PROVINCES) == 77 and len(set(PROVINCES)) == 77


@pytest.mark.parametrize("name", PROVINCES)
def test_exact(name):
    got, score = match_province(name)
    assert got == name and score == 100


@pytest.mark.parametrize("ocr,expected", [
    ("กรุงเทพมหานคค", "กรุงเทพมหานคร"),
    ("กรงเทพมหานคร", "กรุงเทพมหานคร"),
    ("เชยงใหม่", "เชียงใหม่"),
    ("นครราชสีมา.", "นครราชสีมา"),
    ("สมุทรปราการ ", "สมุทรปราการ"),
    ("อุบลราชธาน", "อุบลราชธานี"),
    ("พระนครศรีอยุธยา", "พระนครศรีอยุธยา"),
    ("อยุธยา", "พระนครศรีอยุธยา"),
    ("กรุงเทพ", "กรุงเทพมหานคร"),
    ("เบตง", "เบตง"),
])
def test_fuzzy(ocr, expected):
    got, score = match_province(ocr)
    assert got == expected, (ocr, got, score)
    assert score >= 80


@pytest.mark.parametrize("junk", ["", "ก", "abc", "1234", "สวัสดีครับทุกคน"])
def test_reject(junk):
    got, _ = match_province(junk)
    assert got is None


def test_min_score_respected():
    got, score = match_province("เชยงใม", min_score=95)
    assert got is None and score < 95
