"""การจับคู่เข้า-ออก"""
from lpr import constants as C
from lpr.events.visits import format_duration_th, mark_overstay, rebuild, step

IN, OUT = C.DIR_IN, C.DIR_OUT
H = 3600.0


def test_simple_pair():
    v = rebuild([(1, 0.0, IN), (2, 2 * H + 30 * 60, OUT)])
    assert len(v) == 1
    assert v[0].status == C.VISIT_DONE and v[0].duration_sec == 2 * H + 1800
    assert (v[0].entry_event_id, v[0].exit_event_id) == (1, 2)


def test_inside_now():
    v = rebuild([(1, 0.0, IN)])
    assert v[0].status == C.VISIT_INSIDE and v[0].exit_event_id is None


def test_exit_without_entry():
    v = rebuild([(5, 100.0, OUT)])
    assert v[0].status == C.VISIT_NO_ENTRY and v[0].entry_event_id is None


def test_double_entry_marks_no_exit():
    v = rebuild([(1, 0.0, IN), (2, 10 * H, IN), (3, 11 * H, OUT)])
    assert [x.status for x in v] == [C.VISIT_NO_EXIT, C.VISIT_DONE]
    assert v[1].entry_event_id == 2 and v[1].exit_event_id == 3 and v[1].duration_sec == H


def test_double_exit():
    v = rebuild([(1, 0.0, IN), (2, H, OUT), (3, 2 * H, OUT)])
    assert [x.status for x in v] == [C.VISIT_DONE, C.VISIT_NO_ENTRY]


def test_unsorted_input_is_sorted():
    v = rebuild([(2, H, OUT), (1, 0.0, IN)])
    assert len(v) == 1 and v[0].status == C.VISIT_DONE


def test_overstay():
    v = rebuild([(1, 0.0, IN)], now=25 * H, overstay_sec=24 * H)
    assert v[0].status == C.VISIT_NO_EXIT
    v2 = rebuild([(1, 0.0, IN)], now=23 * H, overstay_sec=24 * H)
    assert v2[0].status == C.VISIT_INSIDE


def test_exit_after_overstay_still_pairs():
    v = rebuild([(1, 0.0, IN)], now=30 * H, overstay_sec=24 * H)
    upd, new = step(v[-1], 2, 30 * H, OUT)
    assert new is None and upd is not None and upd.status == C.VISIT_DONE and upd.duration_sec == 30 * H


def test_mark_overstay_leaves_closed():
    v = rebuild([(1, 0.0, IN), (2, H, OUT)])[0]
    assert mark_overstay(v, 100 * H, 24 * H).status == C.VISIT_DONE


def test_duration_text():
    assert format_duration_th(2 * H + 15 * 60) == "2 ชม. 15 น."
    assert format_duration_th(45 * 60) == "45 น."
    assert format_duration_th(3 * H) == "3 ชม."
    assert format_duration_th(None) == "-"
