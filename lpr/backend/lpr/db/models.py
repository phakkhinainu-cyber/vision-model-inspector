"""ตารางฐานข้อมูล (SQLite โหมด WAL)

เวลาทุกช่อง (ts, first_seen, ...) เก็บเป็น Unix epoch วินาที (REAL, UTC) แสดงผลเป็นเวลา Asia/Bangkok
path ของภาพเก็บแบบ relative กับโฟลเดอร์ data เพื่อให้ย้ายโฟลเดอร์ได้
"""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    rtsp_main: Mapped[str] = mapped_column(Text, default="")
    rtsp_sub: Mapped[str] = mapped_column(Text, default="")
    username: Mapped[str] = mapped_column(String(100), default="")  # รหัสผ่านเก็บใน Windows Credential Manager
    role: Mapped[str] = mapped_column(String(20), default="สองทาง")
    roi_polygon: Mapped[str] = mapped_column(Text, default="[]")  # JSON [[x,y],...] 0..1
    line_coords: Mapped[str] = mapped_column(Text, default="[]")  # JSON [[x1,y1],[x2,y2]] 0..1
    line_direction: Mapped[str] = mapped_column(String(10), default="pos_in")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("plate_norm", "province", name="uq_vehicle_plate_province"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_norm: Mapped[str] = mapped_column(String(20), index=True)
    province: Mapped[str] = mapped_column(String(40), default="")
    vehicle_type: Mapped[str] = mapped_column(String(30), default="")
    type_locked: Mapped[bool] = mapped_column(Boolean, default=False)  # ผู้ใช้กำหนดประเภทเอง
    status: Mapped[str] = mapped_column(String(20), default="ไม่รู้จัก", index=True)
    owner_name: Mapped[str] = mapped_column(String(120), default="")
    house_no: Mapped[str] = mapped_column(String(40), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    first_seen: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[float | None] = mapped_column(Float, nullable=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_ts", "ts"),
        Index("ix_events_cam_plate_ts", "camera_id", "plate_norm", "ts"),
        Index("ix_events_review", "review_status", "ts"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(40), unique=True)
    ts: Mapped[float] = mapped_column(Float)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    direction: Mapped[str] = mapped_column(String(10))
    plate_raw: Mapped[str] = mapped_column(Text, default="")
    plate_norm: Mapped[str] = mapped_column(String(20), default="", index=True)
    province: Mapped[str] = mapped_column(String(40), default="")
    ocr_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    vehicle_type: Mapped[str] = mapped_column(String(30), default="")
    plate_color: Mapped[str] = mapped_column(String(30), default="")
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True)
    image_full_path: Mapped[str] = mapped_column(Text, default="")
    image_plate_path: Mapped[str] = mapped_column(Text, default="")
    image_thumb_path: Mapped[str] = mapped_column(Text, default="")
    clip_path: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(20), default="ปกติ")
    original_plate: Mapped[str] = mapped_column(String(80), default="")
    edited_by: Mapped[str] = mapped_column(String(80), default="")
    edited_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="auto")
    yolo_class: Mapped[str] = mapped_column(String(20), default="")
    frames_used: Mapped[int] = mapped_column(Integer, default=0)
    night: Mapped[bool] = mapped_column(Boolean, default=False)
    alternatives: Mapped[str] = mapped_column(Text, default="[]")  # JSON ผลอ่านอันดับรองจากการโหวต
    note: Mapped[str] = mapped_column(Text, default="")


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (Index("ix_visits_vehicle", "vehicle_id", "status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    entry_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    exit_event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    entry_ts: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    exit_ts: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="อยู่ในพื้นที่", index=True)
    alerted: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(10), default="viewer")
    display_name: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[float] = mapped_column(Float, default=0.0)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = mapped_column(Float, index=True)
    user: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(Text, default="")


class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    user_agent: Mapped[str] = mapped_column(Text, default="")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float)
