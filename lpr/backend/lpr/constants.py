"""ค่าคงที่ที่ใช้ร่วมกันทั้งโปรแกรม (ข้อความภาษาไทยที่เก็บในฐานข้อมูล)"""
from __future__ import annotations

DIR_IN = "เข้า"
DIR_OUT = "ออก"
DIRECTIONS = (DIR_IN, DIR_OUT)

REVIEW_OK = "ปกติ"
REVIEW_PENDING = "รอตรวจสอบ"
REVIEW_EDITED = "แก้ไขแล้ว"
REVIEW_UNREAD = "อ่านไม่ได้"
REVIEW_STATUSES = (REVIEW_OK, REVIEW_PENDING, REVIEW_EDITED, REVIEW_UNREAD)

VS_MEMBER = "สมาชิก"
VS_VISITOR = "ผู้มาเยือน"
VS_UNKNOWN = "ไม่รู้จัก"
VS_WATCH = "เฝ้าระวัง"
VEHICLE_STATUSES = (VS_MEMBER, VS_VISITOR, VS_UNKNOWN, VS_WATCH)

VT_SEDAN = "รถเก๋ง"
VT_PICKUP = "รถกระบะ"
VT_VAN = "รถตู้"
VT_MOTORCYCLE = "รถจักรยานยนต์"
VT_TRUCK = "รถบรรทุก"
VT_TAXI = "แท็กซี่/รับจ้าง"
VT_BUS = "รถบัส"
VT_RED = "ป้ายแดง"
VT_OTHER = "อื่นๆ"
VEHICLE_TYPES = (VT_SEDAN, VT_PICKUP, VT_VAN, VT_MOTORCYCLE, VT_TRUCK, VT_TAXI, VT_BUS, VT_RED, VT_OTHER)

ROLE_IN = "ทางเข้า"
ROLE_OUT = "ทางออก"
ROLE_BOTH = "สองทาง"
CAMERA_ROLES = (ROLE_IN, ROLE_OUT, ROLE_BOTH)

# ทิศที่รถข้ามเส้นเสมือน: "pos" = ข้ามจากด้านซ้ายของเส้น (มองจากจุด A ไป B) ไปด้านขวา
LINE_POS_IN = "pos_in"
LINE_NEG_IN = "neg_in"

VISIT_INSIDE = "อยู่ในพื้นที่"
VISIT_DONE = "ออกแล้ว"
VISIT_NO_EXIT = "ไม่พบการออก"
VISIT_NO_ENTRY = "ไม่พบการเข้า"

SOURCE_AUTO = "auto"
SOURCE_CAPTURE = "capture"
SOURCE_MANUAL = "manual"

COLOR_TH = {
    "white": "ขาว", "yellow": "เหลือง", "red": "แดง", "green": "เขียว",
    "blue": "น้ำเงิน", "black": "ดำ", "orange": "ส้ม", "unknown": "ไม่ทราบ",
}

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
