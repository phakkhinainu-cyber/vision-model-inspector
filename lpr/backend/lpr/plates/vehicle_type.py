"""รวมผลประเภทรถจาก YOLO และสีป้าย/รูปแบบป้าย"""
from __future__ import annotations

from .. import constants as C

YOLO_CLASS_TH = {"car": "รถยนต์", "motorcycle": C.VT_MOTORCYCLE, "bus": C.VT_BUS, "truck": C.VT_TRUCK}


def merge_vehicle_type(yolo_cls: str | None, plate_bg: str, plate_fg: str, plate_kind: str,
                       plate_lines: int = 2) -> str:
    """yolo_cls: car | motorcycle | bus | truck | None"""
    if plate_bg == "red":
        return C.VT_RED
    if yolo_cls == "motorcycle" or plate_lines >= 3:
        return C.VT_MOTORCYCLE
    if yolo_cls == "bus":
        return C.VT_BUS
    if plate_bg == "yellow":
        return C.VT_TRUCK if (yolo_cls == "truck" and plate_kind == "public") else C.VT_TAXI
    if plate_kind == "public":
        return C.VT_TRUCK if yolo_cls == "truck" else C.VT_TAXI
    if plate_bg == "white" and plate_fg == "green":
        return C.VT_PICKUP
    if plate_bg == "white" and plate_fg == "blue":
        return C.VT_VAN
    if yolo_cls == "truck":
        # COCO มักจัดรถกระบะเป็น truck
        return C.VT_PICKUP
    if yolo_cls == "car":
        return C.VT_SEDAN
    return C.VT_OTHER
