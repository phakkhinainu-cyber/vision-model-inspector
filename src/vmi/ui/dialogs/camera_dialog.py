"""หน้าต่างเลือกกล้อง: USB/ในเครื่อง (Qt Multimedia), ระบุเอง (OpenCV index/backend), IP Camera (RTSP)."""
from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from ...config import redact
from ...sources.credentials import build_url, dpapi_available, protect, strip_credentials, unprotect
from ...sources.opencv_source import OpenCVSource
from ..widgets import bgr_to_pixmap
from ..workers import SourceBridge

log = logging.getLogger(__name__)

INDUSTRIAL_NOTE = ("กล้องอุตสาหกรรม (GigE Vision / USB3 Vision เช่น Basler, FLIR, Hikrobot) "
                   "มักต้องใช้ SDK ของผู้ผลิตและ adapter เฉพาะ — รุ่นนี้ยังไม่รองรับโดยตรง "
                   "หากผู้ผลิตมีไดรเวอร์ DirectShow/Media Foundation อาจใช้ผ่านแท็บ 'ระบุเอง' ได้")


def make_source(choice: dict, parent=None):
    """Create a FrameSource from a camera choice dict."""
    k = choice.get("kind")
    if k == "qt-camera":
        from ...sources.qt_camera import QtCameraSource
        return QtCameraSource(choice["ident"], choice["name"], choice.get("fmt"), parent=parent)
    if k == "opencv-index":
        return OpenCVSource("opencv-index", int(choice["index"]), choice["name"],
                            backend=choice.get("backend", "auto"),
                            open_timeout=float(choice.get("timeout", 8)), reconnects=1,
                            width=int(choice.get("w", 0)), height=int(choice.get("h", 0)),
                            fps=float(choice.get("fps", 0)))
    if k == "rtsp":
        pwd = choice.get("password_session") or unprotect(choice.get("secret", ""))
        url = build_url(choice["url"], choice.get("user", ""), pwd)
        return OpenCVSource("rtsp", url, choice["name"], open_timeout=float(choice.get("timeout", 8)),
                            reconnects=int(choice.get("reconnects", 3)))
    raise ValueError(f"unknown camera kind {k}")


class _Preview(QWidget):
    """Test-view used by all tabs; streams until stopped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QLabel("กด 'ทดสอบภาพ' เพื่อดูภาพตัวอย่าง")
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setMinimumSize(QSize(360, 220))
        self.view.setStyleSheet("background:#0F1730;color:#A9B4D6;border-radius:6px;")
        self.info = QLabel("")
        self.info.setObjectName("Hint")
        self.info.setWordWrap(True)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.info)
        self.src = None
        self.bridge = None
        self._n = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self, choice: dict):
        self.stop()
        try:
            self.src = make_source(choice, self)
        except Exception as e:
            self.info.setText(f"สร้างแหล่งภาพไม่ได้: {e}")
            return
        self.bridge = SourceBridge(self)
        self.bridge.attach(self.src)
        self.bridge.frame.connect(self._frame)
        self.bridge.status.connect(lambda m: self.info.setText(redact(m)))
        self.bridge.error.connect(lambda m: self.info.setText("⚠ " + redact(m)))
        self.view.setText("กำลังเชื่อมต่อ …")
        self._n = 0
        self.src.start()
        self._timer.start(500)

    def _frame(self, pkt):
        self._n += 1
        if self._n % 2 == 1:
            pm = bgr_to_pixmap(pkt.image).scaled(self.view.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
            self.view.setPixmap(pm)

    def _tick(self):
        if self.src and self.src.actual_resolution:
            w, h = self.src.actual_resolution
            fps = self.src.capture_fps.fps
            self.info.setText(f"ใช้งานจริง: {w} × {h} • {fps:.1f} FPS (วัดจากเฟรมที่ได้รับ)")

    def stop(self):
        self._timer.stop()
        if self.src is not None:
            try:
                self.src.on_frame = None
                self.src.stop()
            except Exception:
                pass
            self.src = None
        self.view.clear()
        self.view.setText("หยุดทดสอบแล้ว")


class CameraDialog(QDialog):
    def __init__(self, settings, current: dict | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.choice = None
        self.setWindowTitle("เลือกกล้อง")
        self.resize(980, 600)
        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.tabs = QTabWidget()
        body.addWidget(self.tabs, 3)
        right = QVBoxLayout()
        self.preview = _Preview(self)
        right.addWidget(self.preview, 1)
        rb = QHBoxLayout()
        self.b_test = QPushButton("ทดสอบภาพ")
        self.b_test.setProperty("kind", "primary")
        self.b_test.clicked.connect(self._test)
        self.b_stop = QPushButton("หยุด / ยกเลิก")
        self.b_stop.clicked.connect(self.preview.stop)
        rb.addWidget(self.b_test)
        rb.addWidget(self.b_stop)
        right.addLayout(rb)
        body.addLayout(right, 2)

        self._build_usb_tab()
        self._build_manual_tab()
        self._build_rtsp_tab()

        note = QLabel(INDUSTRIAL_NOTE)
        note.setWordWrap(True)
        note.setObjectName("Hint")
        root.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("ใช้แหล่งภาพนี้")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("ปิด")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self.refresh()

    # ------------------------------------------------------------ USB
    def _build_usb_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("อุปกรณ์ที่ Windows/Qt Multimedia มองเห็น"))
        top.addStretch(1)
        b = QPushButton("รีเฟรชรายการ")
        b.clicked.connect(self.refresh)
        top.addWidget(b)
        lay.addLayout(top)
        self.cam_table = QTableWidget(0, 4)
        self.cam_table.setHorizontalHeaderLabels(["ชื่ออุปกรณ์", "ประเภท / รายละเอียด", "Backend", "สถานะ"])
        self.cam_table.verticalHeader().setVisible(False)
        self.cam_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cam_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cam_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cam_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cam_table.itemSelectionChanged.connect(self._cam_selected)
        lay.addWidget(self.cam_table, 1)
        f = QFormLayout()
        self.fmt_combo = QComboBox()
        f.addRow("ความละเอียด / FPS ที่อุปกรณ์รายงาน:", self.fmt_combo)
        lay.addLayout(f)
        self.usb_msg = QLabel("")
        self.usb_msg.setWordWrap(True)
        self.usb_msg.setObjectName("Hint")
        lay.addWidget(self.usb_msg)
        self.tabs.addTab(w, "กล้อง USB / ในเครื่อง")
        self._cams = []

    def refresh(self):
        self.preview.stop()
        try:
            from ...sources.qt_camera import list_qt_cameras
            self._cams = list_qt_cameras()
            err = ""
        except Exception as e:
            self._cams, err = [], str(e)
        self.cam_table.setRowCount(len(self._cams))
        for r, c in enumerate(self._cams):
            for col, v in enumerate((c.name, c.detail, c.backend, "พบอุปกรณ์")):
                self.cam_table.setItem(r, col, QTableWidgetItem(v))
        if err:
            self.usb_msg.setText(f"ค้นหากล้องไม่ได้: {err}")
        elif not self._cams:
            self.usb_msg.setText("ไม่พบกล้อง — ตรวจการเชื่อมต่อ USB, สิทธิ์กล้องใน Windows "
                                 "(Settings › Privacy & security › Camera) หรือใช้แท็บ 'ระบุเอง'")
        else:
            self.usb_msg.setText(f"พบ {len(self._cams)} อุปกรณ์ • เลือกแล้วกด 'ทดสอบภาพ' เพื่อตรวจภาพจริง")
            self.cam_table.selectRow(0)

    def _cam_selected(self):
        self.fmt_combo.clear()
        r = self.cam_table.currentRow()
        if r < 0 or r >= len(self._cams):
            return
        self.fmt_combo.addItem("ค่าเริ่มต้นของอุปกรณ์", None)
        for f in self._cams[r].extra.get("formats", []):
            fps = f"{f['max_fps']:.0f}" if f["min_fps"] == f["max_fps"] else f"{f['min_fps']:.0f}–{f['max_fps']:.0f}"
            self.fmt_combo.addItem(f"{f['w']} × {f['h']} @ {fps} FPS ({f['pixel']})", f)

    def _usb_choice(self):
        r = self.cam_table.currentRow()
        if r < 0 or r >= len(self._cams):
            return None
        c = self._cams[r]
        return {"kind": "qt-camera", "ident": c.ident, "name": c.name, "detail": c.detail,
                "fmt": self.fmt_combo.currentData()}

    # ------------------------------------------------------------ manual
    def _build_manual_tab(self):
        w = QWidget()
        f = QFormLayout(w)
        info = QLabel("ใช้เมื่อกล้องไม่ปรากฏในรายการอัตโนมัติ — ระบุ index และ backend ของ OpenCV เอง "
                      "แล้วกดทดสอบ (ไม่รับประกันว่าทุกอุปกรณ์ใน Device Manager จะเปิดได้)")
        info.setWordWrap(True)
        f.addRow(info)
        self.m_index = QSpinBox()
        self.m_index.setRange(0, 63)
        self.m_backend = QComboBox()
        for k, t in (("dshow", "DirectShow (DSHOW)"), ("msmf", "Media Foundation (MSMF)"),
                     ("auto", "อัตโนมัติ (CAP_ANY)"), ("v4l2", "V4L2 (Linux)")):
            self.m_backend.addItem(t, k)
        self.m_w = QSpinBox(); self.m_w.setRange(0, 8192); self.m_w.setSpecialValueText("ค่าเริ่มต้น")
        self.m_h = QSpinBox(); self.m_h.setRange(0, 8192); self.m_h.setSpecialValueText("ค่าเริ่มต้น")
        self.m_fps = QDoubleSpinBox(); self.m_fps.setRange(0, 240); self.m_fps.setSpecialValueText("ค่าเริ่มต้น")
        self.m_timeout = QDoubleSpinBox(); self.m_timeout.setRange(2, 60); self.m_timeout.setValue(8)
        f.addRow("Index:", self.m_index)
        f.addRow("Backend:", self.m_backend)
        f.addRow("ความกว้างที่ขอ:", self.m_w)
        f.addRow("ความสูงที่ขอ:", self.m_h)
        f.addRow("FPS ที่ขอ:", self.m_fps)
        f.addRow("Timeout เปิดกล้อง (วินาที):", self.m_timeout)
        hint = QLabel("ค่าที่ใช้งานได้จริงจะแสดงหลังเชื่อมต่อ (อุปกรณ์อาจไม่รองรับค่าที่ขอ)")
        hint.setObjectName("Hint")
        f.addRow(hint)
        self.tabs.addTab(w, "ระบุเอง (ขั้นสูง)")

    def _manual_choice(self):
        b = self.m_backend.currentData()
        return {"kind": "opencv-index", "index": self.m_index.value(), "backend": b,
                "name": f"OpenCV #{self.m_index.value()} ({b.upper()})", "w": self.m_w.value(),
                "h": self.m_h.value(), "fps": self.m_fps.value(), "timeout": self.m_timeout.value()}

    # ------------------------------------------------------------ RTSP
    def _build_rtsp_tab(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QVBoxLayout()
        left.addWidget(QLabel("IP Camera ที่บันทึกไว้"))
        self.ip_list = QListWidget()
        self.ip_list.currentRowChanged.connect(self._ip_selected)
        left.addWidget(self.ip_list, 1)
        bl = QHBoxLayout()
        b_new = QPushButton("เพิ่มใหม่")
        b_new.clicked.connect(self._ip_new)
        b_del = QPushButton("ลบ")
        b_del.clicked.connect(self._ip_delete)
        bl.addWidget(b_new); bl.addWidget(b_del)
        left.addLayout(bl)
        lay.addLayout(left, 1)
        f = QFormLayout()
        self.ip_name = QLineEdit()
        self.ip_url = QLineEdit()
        self.ip_url.setPlaceholderText("rtsp://192.168.1.10:554/stream1")
        self.ip_user = QLineEdit()
        self.ip_pwd = QLineEdit()
        self.ip_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.ip_save_pwd = QCheckBox("จำรหัสผ่าน (เข้ารหัสด้วย Windows DPAPI)")
        self.ip_save_pwd.setEnabled(dpapi_available())
        if not dpapi_available():
            self.ip_save_pwd.setToolTip("ระบบนี้ไม่มี DPAPI — จะไม่บันทึกรหัสผ่าน")
        self.ip_timeout = QDoubleSpinBox(); self.ip_timeout.setRange(2, 60); self.ip_timeout.setValue(8)
        self.ip_retry = QSpinBox(); self.ip_retry.setRange(0, 10); self.ip_retry.setValue(3)
        f.addRow("ชื่อที่แสดง:", self.ip_name)
        f.addRow("RTSP URL:", self.ip_url)
        f.addRow("ผู้ใช้:", self.ip_user)
        f.addRow("รหัสผ่าน:", self.ip_pwd)
        f.addRow("", self.ip_save_pwd)
        f.addRow("Timeout (วินาที):", self.ip_timeout)
        f.addRow("เชื่อมต่อใหม่สูงสุด (ครั้ง):", self.ip_retry)
        b_save = QPushButton("บันทึกรายการ")
        b_save.clicked.connect(self._ip_save)
        f.addRow("", b_save)
        hint = QLabel("ไม่สแกนเครือข่ายอัตโนมัติ • รหัสผ่านไม่ถูกเขียนลง log หรือไฟล์ตั้งค่าแบบข้อความธรรมดา")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        f.addRow(hint)
        lay.addLayout(f, 2)
        self.tabs.addTab(w, "IP Camera (RTSP)")
        self._reload_ip()

    def _reload_ip(self):
        self.ip_list.clear()
        for c in self.settings.ip_cameras:
            self.ip_list.addItem(c.get("name") or c.get("url"))

    def _ip_selected(self, row):
        if row < 0 or row >= len(self.settings.ip_cameras):
            return
        c = self.settings.ip_cameras[row]
        self.ip_name.setText(c.get("name", ""))
        self.ip_url.setText(c.get("url", ""))
        self.ip_user.setText(c.get("user", ""))
        self.ip_pwd.setText("")
        self.ip_pwd.setPlaceholderText("(บันทึกไว้แล้ว)" if c.get("secret") else "")
        self.ip_save_pwd.setChecked(bool(c.get("secret")))
        self.ip_timeout.setValue(float(c.get("timeout", 8)))
        self.ip_retry.setValue(int(c.get("reconnects", 3)))

    def _ip_new(self):
        self.ip_list.clearSelection()
        for wdg in (self.ip_name, self.ip_url, self.ip_user, self.ip_pwd):
            wdg.clear()

    def _ip_delete(self):
        r = self.ip_list.currentRow()
        if 0 <= r < len(self.settings.ip_cameras):
            del self.settings.ip_cameras[r]
            self.settings.save()
            self._reload_ip()

    def _rtsp_choice(self, for_save=False):
        url_raw = self.ip_url.text().strip()
        if not url_raw.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            QMessageBox.warning(self, "IP Camera", "กรุณาระบุ URL ที่ขึ้นต้นด้วย rtsp://")
            return None
        url, u2, p2 = strip_credentials(url_raw)
        user = self.ip_user.text().strip() or u2
        pwd = self.ip_pwd.text() or p2
        row = self.ip_list.currentRow()
        old = self.settings.ip_cameras[row] if 0 <= row < len(self.settings.ip_cameras) else {}
        secret = old.get("secret", "") if not pwd else ""
        if pwd and self.ip_save_pwd.isChecked():
            secret = protect(pwd)
        ch = {"kind": "rtsp", "name": self.ip_name.text().strip() or redact(url), "url": url,
              "user": user, "secret": secret if self.ip_save_pwd.isChecked() else "",
              "timeout": self.ip_timeout.value(), "reconnects": self.ip_retry.value()}
        if not for_save:
            ch["password_session"] = pwd
        return ch

    def _ip_save(self):
        ch = self._rtsp_choice(for_save=True)
        if ch is None:
            return
        row = self.ip_list.currentRow()
        if 0 <= row < len(self.settings.ip_cameras):
            self.settings.ip_cameras[row] = ch
        else:
            self.settings.ip_cameras.append(ch)
        self.settings.save()
        self._reload_ip()

    # ------------------------------------------------------------ common
    def current_choice(self):
        i = self.tabs.currentIndex()
        if i == 0:
            return self._usb_choice()
        if i == 1:
            return self._manual_choice()
        return self._rtsp_choice()

    def _test(self):
        ch = self.current_choice()
        if ch is None:
            self.preview.info.setText("ยังไม่ได้เลือกแหล่งภาพ")
            return
        self.preview.start(ch)

    def _accept(self):
        ch = self.current_choice()
        if ch is None:
            QMessageBox.information(self, "เลือกกล้อง", "กรุณาเลือกกล้องก่อน")
            return
        self.preview.stop()
        self.choice = ch
        self.accept()

    def reject(self):
        self.preview.stop()
        super().reject()
