"""Main window — UI แบบ C ภาษาไทย (วิเคราะห์เปรียบเทียบ)."""
from __future__ import annotations

import datetime as _dt
import logging
import os
import time

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..adapters.registry import supported_extensions
from ..config import AppSettings, redact, user_data_dir
from ..core.classes import ClassRegistry, ClassView, DisplayNameStore, SOURCE_FILE, ClassMappingError, compare_mapping
from ..core.export import export_snapshot
from ..core.imageops import overlay_heatmap
from ..core.snapshots import GradCamRecord, Snapshot, SnapshotStore
from ..core.sysinfo import cuda_status, file_sha256
from ..core.types import FramePacket, InferenceSettings, format_confidence
from ..pipeline.inference_worker import InferenceWorker
from ..sources.image_source import ImageSource
from ..sources.opencv_source import OpenCVSource
from . import theme
from .dialogs.camera_dialog import CameraDialog, make_source
from .dialogs.class_manager import ClassManagerDialog
from .dialogs.export_dialog import ExportDialog
from .dialogs.model_info import ModelInfoDialog
from .icons import icon, pixmap
from .widgets import (Card, DetailPanel, DetectionTable, ImageView, LiveView, SliderRow,
                      SnapshotStrip, ZoomBar, hline, render_detections_qt, tool_button)
from .workers import GradCamThread, InferenceBridge, ModelLoadThread, SourceBridge

log = logging.getLogger(__name__)

GRADCAM_NOTICE = "Grad-CAM วิเคราะห์ภาพที่เลือก ไม่ใช่ภาพสด และแผนที่สีไม่ใช่ค่าความแม่นยำ"
IMGSZ_CHOICES = (320, 416, 480, 512, 640, 736, 800, 960, 1024, 1280)
MODE_CAMERA, MODE_VIDEO, MODE_IMAGE, MODE_FOLDER = "camera", "video", "image", "folder"


def _btn(text, icon_name=None, kind=None, tip="", icon_color=None):
    b = QPushButton(text)
    if icon_name:
        col = icon_color or ("#ffffff" if kind in ("primary", "success") else theme.TEXT)
        b.setIcon(icon(icon_name, col))
        b.setIconSize(QSize(18, 18))
    if kind:
        b.setProperty("kind", kind)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _field(text):
    lab = QLabel(text)
    lab.setObjectName("FieldLabel")
    return lab


class MainWindow(QMainWindow):
    snapshotAdded = Signal(int)
    gradcamFinished = Signal(bool)
    modelLoaded = Signal(bool)

    def __init__(self, settings: AppSettings | None = None):
        super().__init__()
        self.settings = settings or AppSettings.load()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 700)
        self.store = SnapshotStore(self.settings.snapshot_max_items, self.settings.snapshot_max_mb)
        self.names_store = DisplayNameStore(os.path.join(user_data_dir(), "display_names.json"))
        self.adapter = None
        self.class_view: ClassView | None = None
        self.source = None
        self.source_bridge = None
        self.mode = MODE_CAMERA
        self.file_path = ""
        self.current_snap: Snapshot | None = None
        self.selected_det = None
        self._last_frame: FramePacket | None = None
        self._live_pair = None
        self._last_preview_t = 0.0
        self._frame_count = None
        self._task = "พร้อม"
        self._gc_thread = None
        self._load_thread = None
        self._pending_model = None
        self._live_dialog = None
        self._source_state = "ยังไม่ได้เริ่ม"
        self._cuda = cuda_status()

        self.infer_bridge = InferenceBridge(self)
        self.infer_bridge.result.connect(self._on_result)
        self.infer_bridge.error.connect(lambda m: self._set_task("⚠ " + m))
        self.worker = InferenceWorker(on_result=self.infer_bridge.result.emit,
                                      on_error=self.infer_bridge.error.emit)
        self.worker.set_settings(self._inference_settings())
        self.worker.set_rate(self.settings.infer_every_n, self.settings.max_infer_fps)
        self.worker.start()

        self._build_ui()
        self._apply_settings_to_widgets()
        self.refresh_cameras(initial=True)
        self._fill_layers()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(500)
        self._update_states()

    # ================================================================ UI build
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._build_header())
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 10, 12, 8)
        bv.setSpacing(10)
        bv.addWidget(self._build_toolbar())
        bv.addLayout(self._build_top_row())
        bv.addWidget(self._build_main(), 1)
        v.addWidget(body, 1)
        self._build_statusbar()
        self._build_shortcuts()

    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("HeaderBar")
        bar.setFixedHeight(50)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 16, 0)
        h.setSpacing(14)
        logo = QLabel()
        logo.setObjectName("Logo")
        logo.setFixedSize(58, 50)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(pixmap("eye", "#ffffff", 30))
        h.addWidget(logo)
        t = QLabel(APP_NAME)
        t.setObjectName("AppTitle")
        h.addWidget(t)
        sep = QFrame()
        sep.setObjectName("HeaderSep")
        sep.setFixedHeight(26)
        h.addWidget(sep)
        sub = QLabel("แบบ C • วิเคราะห์เปรียบเทียบ")
        sub.setObjectName("AppSubtitle")
        h.addWidget(sub)
        h.addStretch(1)
        self.header_meta = QLabel("ยังไม่ได้เปิดโมเดล")
        self.header_meta.setObjectName("HeaderMeta")
        h.addWidget(self.header_meta)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("HeaderMeta")
        h.addWidget(ver)
        return bar

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName("ToolBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.b_open = _btn("เปิดโมเดล…", "folder", "primary", "เปิดไฟล์โมเดล .pt / .onnx (Ctrl+O)")
        self.b_open.clicked.connect(self.open_model_dialog)
        h.addWidget(self.b_open)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(150)
        self.model_combo.setMaximumWidth(220)
        self.model_combo.setToolTip("โมเดลปัจจุบัน / โมเดลที่เปิดล่าสุด")
        self.model_combo.activated.connect(self._model_combo_activated)
        h.addWidget(self.model_combo)
        h.addSpacing(4)

        self.mode_combo = QComboBox()
        for key, text, ic in ((MODE_CAMERA, "กล้อง", "camera"), (MODE_VIDEO, "วิดีโอ", "play"),
                              (MODE_IMAGE, "รูปภาพ", "image"), (MODE_FOLDER, "โฟลเดอร์ภาพ", "folder")):
            self.mode_combo.addItem(icon(ic, theme.TEXT), text, key)
        self.mode_combo.setToolTip("เลือกแหล่งข้อมูล: กล้อง วิดีโอ รูปภาพ หรือโฟลเดอร์ภาพ")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        h.addWidget(self.mode_combo)

        self.src_stack = QStackedWidget()
        self.src_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cam_w = QWidget()
        ch = QHBoxLayout(cam_w)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(4)
        lab = QLabel()
        lab.setPixmap(pixmap("camera", theme.TEXT, 18))
        ch.addWidget(lab)
        ch.addWidget(QLabel("กล้อง:"))
        self.cam_combo = QComboBox()
        self.cam_combo.setMinimumWidth(170)
        self.cam_combo.activated.connect(self._camera_combo_activated)
        ch.addWidget(self.cam_combo, 1)
        self.b_refresh = tool_button("refresh", "ค้นหาและรีเฟรชรายการกล้อง (F5)")
        self.b_refresh.clicked.connect(lambda: self.refresh_cameras())
        ch.addWidget(self.b_refresh)
        self.b_camcfg = tool_button("settings", "เลือกกล้อง / ทดสอบภาพ / IP Camera / ระบุเอง…")
        self.b_camcfg.clicked.connect(self.open_camera_dialog)
        ch.addWidget(self.b_camcfg)
        self.src_stack.addWidget(cam_w)
        file_w = QWidget()
        fh = QHBoxLayout(file_w)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(4)
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText("ยังไม่ได้เลือกไฟล์")
        fh.addWidget(self.file_edit, 1)
        self.b_browse = _btn("เลือก…", tip="เลือกไฟล์/โฟลเดอร์")
        self.b_browse.clicked.connect(self.browse_source)
        fh.addWidget(self.b_browse)
        self.src_stack.addWidget(file_w)
        h.addWidget(self.src_stack, 1)

        self.b_start = _btn("เริ่ม", "play", "success", "เริ่มรับภาพและตรวจจับ")
        self.b_start.clicked.connect(self.start_source)
        self.b_stop = _btn("หยุด", "stop", None, "หยุดแหล่งภาพ")
        self.b_stop.clicked.connect(self.stop_source)
        self.b_pause = tool_button("pause", "หยุดวิดีโอชั่วคราว / เล่นต่อ", checkable=True)
        self.b_pause.toggled.connect(self._toggle_pause)
        self.b_capture = _btn("จับภาพ", "camera", None, "บันทึก snapshot พร้อมผลตรวจจับ (Space)")
        self.b_capture.clicked.connect(self.capture_snapshot)
        self.b_gradcam = _btn("วิเคราะห์", "chart", "primary", "วิเคราะห์ Grad-CAM ของวัตถุที่เลือก (Ctrl+G)")
        self.b_gradcam.clicked.connect(self.run_gradcam)
        self.b_export = _btn("ส่งออก…", "export", None, "ส่งออกภาพ CSV และ metadata (Ctrl+E)")
        self.b_export.clicked.connect(self.export_current)
        for w in (self.b_start, self.b_stop, self.b_pause, self.b_capture, self.b_gradcam, self.b_export):
            h.addWidget(w)
        return bar

    def _build_top_row(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        # live card
        live = QFrame()
        live.setObjectName("LiveCard")
        live.setFixedWidth(400)
        live.setFixedHeight(168)
        lv = QVBoxLayout(live)
        lv.setContentsMargins(8, 6, 8, 8)
        lv.setSpacing(4)
        hh = QHBoxLayout()
        self.live_dot = QFrame()
        self.live_dot.setFixedSize(10, 10)
        self._set_dot(False)
        hh.addWidget(self.live_dot)
        t = QLabel("ภาพสด")
        t.setObjectName("LiveTitle")
        hh.addWidget(t)
        self.live_meta = QLabel("—")
        self.live_meta.setStyleSheet("color:#C9D2EA;")
        hh.addWidget(self.live_meta, 1)
        self.live_badge = QLabel("")
        self.live_badge.setObjectName("Badge")
        self.live_badge.hide()
        hh.addWidget(self.live_badge)
        self.b_prev_img = tool_button("left", "ภาพก่อนหน้า", "#ffffff", size=16)
        self.b_next_img = tool_button("right", "ภาพถัดไป", "#ffffff", size=16)
        self.b_prev_img.clicked.connect(lambda: self._step_image(-1))
        self.b_next_img.clicked.connect(lambda: self._step_image(1))
        hh.addWidget(self.b_prev_img)
        hh.addWidget(self.b_next_img)
        b_exp = tool_button("expand", "ขยายดูภาพสด", "#ffffff", size=16)
        b_exp.clicked.connect(self.open_live_viewer)
        hh.addWidget(b_exp)
        lv.addLayout(hh)
        self.live_view = LiveView()
        lv.addWidget(self.live_view, 1)
        row.addWidget(live)

        # snapshot strip
        strip_card = QFrame()
        strip_card.setObjectName("Card")
        strip_card.setFixedHeight(168)
        sv = QVBoxLayout(strip_card)
        sv.setContentsMargins(10, 6, 6, 4)
        sv.setSpacing(2)
        sh = QHBoxLayout()
        self.strip_title = QLabel("ภาพที่บันทึก (0)")
        self.strip_title.setObjectName("CardTitle")
        sh.addWidget(self.strip_title)
        self.strip_info = QLabel("")
        self.strip_info.setObjectName("Hint")
        sh.addWidget(self.strip_info, 1)
        b_del = tool_button("trash", "ลบภาพที่เลือกออกจากรายการ (Delete)")
        b_del.clicked.connect(self.delete_current_snapshot)
        sh.addWidget(b_del)
        sv.addLayout(sh)
        srow = QHBoxLayout()
        srow.setSpacing(2)
        bl = tool_button("left", "เลื่อนซ้าย")
        br = tool_button("right", "เลื่อนขวา")
        self.strip = SnapshotStrip()
        bl.clicked.connect(lambda: self.strip.scroll_by(-260))
        br.clicked.connect(lambda: self.strip.scroll_by(260))
        self.strip.currentItemChanged.connect(lambda *_: self._strip_selected())
        self.strip.itemDoubleClicked.connect(lambda *_: self.open_snapshot_viewer())
        self.strip.customContextMenuRequested.connect(self._strip_menu)
        srow.addWidget(bl)
        srow.addWidget(self.strip, 1)
        srow.addWidget(br)
        sv.addLayout(srow)
        row.addWidget(strip_card, 1)

        # info banner
        info = QFrame()
        info.setObjectName("InfoBanner")
        info.setFixedWidth(300)
        info.setFixedHeight(168)
        iv = QVBoxLayout(info)
        iv.setContentsMargins(12, 10, 12, 10)
        ih = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap("info", "#2F6FD6", 22))
        ic.setAlignment(Qt.AlignmentFlag.AlignTop)
        ih.addWidget(ic)
        msg = QLabel(GRADCAM_NOTICE)
        msg.setWordWrap(True)
        ih.addWidget(msg, 1)
        iv.addLayout(ih)
        self.model_summary = QLabel("เปิดโมเดล (.pt / .onnx) เพื่อเริ่มตรวจจับ")
        self.model_summary.setWordWrap(True)
        self.model_summary.setObjectName("Hint")
        self.model_summary.setStyleSheet(f"color:{theme.INFO_FG};")
        iv.addWidget(self.model_summary, 1)
        row.addWidget(info)
        return row

    def _set_dot(self, on: bool):
        c = "#38D16A" if on else "#7E879E"
        self.live_dot.setStyleSheet(f"background:{c};border-radius:5px;border:none;")

    def _build_main(self):
        self.hsplit = QSplitter(Qt.Orientation.Horizontal)
        self.hsplit.setChildrenCollapsible(False)
        self.hsplit.setHandleWidth(10)

        # ---- left column: analysed snapshot + table
        self.left_split = QSplitter(Qt.Orientation.Vertical)
        self.left_split.setHandleWidth(10)
        self.det_card = Card("วิเคราะห์ภาพที่จับไว้ • ผลการตรวจ", accent=True)
        self.det_view = ImageView()
        self.det_view.set_placeholder("ยังไม่มีภาพที่บันทึก — กด 'เริ่ม' แล้ว 'จับภาพ'")
        self.det_view.detectionClicked.connect(self.select_detection)
        self.det_card.body_layout.addWidget(self.det_view, 1)
        dfoot = QHBoxLayout()
        dfoot.setSpacing(6)
        dfoot.addWidget(ZoomBar(self.det_view))
        self.sync_cb = QCheckBox("ซิงก์มุมมองสองฝั่ง")
        self.sync_cb.setToolTip("ซูม/เลื่อนภาพทั้งสองฝั่งพร้อมกัน")
        dfoot.addWidget(self.sync_cb)
        dfoot.addStretch(1)
        self.det_view.setToolTip("ล้อเมาส์ = ซูม • ลาก = เลื่อน • ดับเบิลคลิก = พอดีกรอบ • คลิกกรอบ = เลือกวัตถุ")
        self.det_card.body_layout.addLayout(dfoot)
        self.left_split.addWidget(self.det_card)
        self.table_card = Card("วัตถุที่ตรวจพบ  (จากภาพที่จับไว้)")
        self.table_card.setMinimumHeight(200)
        self.table = DetectionTable()
        self.table.detectionSelected.connect(self.select_detection)
        self.table_card.body_layout.setContentsMargins(0, 0, 0, 0)
        self.table_card.body_layout.addWidget(self.table)
        self.filter_note = QLabel("")
        self.filter_note.setObjectName("Hint")
        self.filter_note.setContentsMargins(8, 0, 8, 4)
        self.table_card.body_layout.addWidget(self.filter_note)
        self.left_split.addWidget(self.table_card)
        self.left_split.setStretchFactor(0, 3)
        self.left_split.setStretchFactor(1, 1)

        # ---- middle column: Grad-CAM + detail
        self.mid_split = QSplitter(Qt.Orientation.Vertical)
        self.mid_split.setHandleWidth(10)
        self.gc_card = Card("วิเคราะห์ Grad-CAM • วัตถุที่เลือก: -", accent=True)
        self.gc_view = ImageView()
        self.gc_view.set_placeholder("เลือกวัตถุจากภาพที่จับไว้ แล้วกด 'วิเคราะห์'")
        self.gc_card.body_layout.addWidget(self.gc_view, 1)
        gfoot = QHBoxLayout()
        gfoot.setSpacing(6)
        gfoot.addWidget(ZoomBar(self.gc_view))
        self.gc_note = QLabel("")
        self.gc_note.setObjectName("Hint")
        self.gc_note.setMinimumWidth(10)
        self.gc_note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        gfoot.addWidget(self.gc_note, 1)
        self.gc_card.body_layout.addLayout(gfoot)
        self.mid_split.addWidget(self.gc_card)
        self.detail_card = Card("ตัวอย่างวัตถุที่เลือก: -")
        self.detail_card.setMinimumHeight(200)
        self.detail = DetailPanel()
        self.detail.clear()
        self.detail_card.body_layout.addWidget(self.detail)
        self.mid_split.addWidget(self.detail_card)
        self.mid_split.setStretchFactor(0, 3)
        self.mid_split.setStretchFactor(1, 1)
        self._user_split = False

        def moved_left(*_):
            self._user_split = True
            self.mid_split.setSizes(self.left_split.sizes())

        def moved_mid(*_):
            self._user_split = True
            self.left_split.setSizes(self.mid_split.sizes())
        self.left_split.splitterMoved.connect(moved_left)
        self.mid_split.splitterMoved.connect(moved_mid)

        self.det_view.viewChanged.connect(lambda: self._sync(self.det_view, self.gc_view))
        self.gc_view.viewChanged.connect(lambda: self._sync(self.gc_view, self.det_view))

        self.hsplit.addWidget(self.left_split)
        self.hsplit.addWidget(self.mid_split)
        self.hsplit.addWidget(self._build_settings_panel())
        self.hsplit.setStretchFactor(0, 5)
        self.hsplit.setStretchFactor(1, 5)
        self.hsplit.setStretchFactor(2, 0)
        QTimer.singleShot(0, self._equalize_splitters)
        return self.hsplit

    def _equalize_splitters(self):
        if getattr(self, "_user_split", True) or not hasattr(self, "mid_split"):
            return
        total = self.left_split.height()
        if total < 200:
            return
        bottom = max(205, min(260, int(total * 0.30)))
        self.left_split.setSizes([total - bottom, bottom])
        self.mid_split.setSizes([total - bottom, bottom])
        sizes = self.hsplit.sizes()
        if len(sizes) == 3 and sum(sizes) > 0:
            side = max(self.hsplit.widget(2).minimumWidth(), min(320, sizes[2]))
            half = (sum(sizes) - side) // 2
            self.hsplit.setSizes([half, sum(sizes) - side - half, side])

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._equalize_splitters)
        QTimer.singleShot(150, self._equalize_splitters)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._equalize_splitters)

    def _build_settings_panel(self):
        card = Card("ตั้งค่า Grad-CAM และการตรวจจับ")
        card.setMinimumWidth(285)
        card.setMaximumWidth(340)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("SettingsInner")
        inner.setMinimumWidth(0)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        lay.addWidget(_field("วัตถุเป้าหมาย"))
        self.target_combo = QComboBox()
        self.target_combo.setToolTip("เลือก detection instance (รหัสวัตถุ • คลาส • confidence)")
        self.target_combo.activated.connect(
            lambda i: self.select_detection(self.target_combo.itemData(i)) if i >= 0 else None)
        lay.addWidget(self.target_combo)
        lay.addWidget(_field("ชั้นเป้าหมาย"))
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(lambda *_: self._show_gradcam())
        lay.addWidget(self.layer_combo)
        lay.addWidget(_field("วิธีคำนวณ"))
        self.method_combo = QComboBox()
        from ..gradcam.ultralytics_gradcam import UltralyticsGradCAM
        for key, label in UltralyticsGradCAM.METHODS:
            self.method_combo.addItem(label, key)
        self.method_combo.setToolTip("Grad-CAM: เฉลี่ย gradient ทั้งแผนที่ (อาจเน้นวัตถุคลาสเดียวกันหลายชิ้น)\n"
                                     "HiResCAM: คง gradient รายตำแหน่ง — ตรงกับวัตถุที่เลือกมากกว่า")
        self.method_combo.currentIndexChanged.connect(lambda *_: self._show_gradcam())
        lay.addWidget(self.method_combo)
        lay.addWidget(_field("ความทึบแผนที่สี"))
        self.opacity = SliderRow(0.0, 1.0, 0.05, 0.5, left_hint="โปร่ง", right_hint="ทึบ")
        self.opacity.valueChanged.connect(lambda *_: self._show_gradcam(render_only=True))
        lay.addWidget(self.opacity)
        lay.addWidget(hline())

        sec = QLabel("การตรวจจับ")
        sec.setObjectName("SectionTitle")
        lay.addWidget(sec)
        lay.addWidget(_field("เกณฑ์ความมั่นใจ"))
        self.conf = SliderRow(0.01, 0.99, 0.01, 0.25)
        self.conf.valueChanged.connect(self._settings_changed)
        lay.addWidget(self.conf)
        lay.addWidget(_field("เกณฑ์ IoU (NMS)"))
        self.iou = SliderRow(0.05, 0.95, 0.01, 0.45)
        self.iou.valueChanged.connect(self._settings_changed)
        lay.addWidget(self.iou)
        lay.addWidget(_field("ขนาด input"))
        self.imgsz_combo = QComboBox()
        self.imgsz_combo.currentIndexChanged.connect(self._settings_changed)
        lay.addWidget(self.imgsz_combo)
        lay.addWidget(_field("อัตราการตรวจจับสด"))
        rate = QHBoxLayout()
        self.every_n = QSpinBox()
        self.every_n.setRange(1, 60)
        self.every_n.setPrefix("ทุก ")
        self.every_n.setSuffix(" เฟรม")
        self.every_n.setToolTip("ตรวจจับทุก N เฟรมที่ได้รับ")
        self.every_n.valueChanged.connect(self._rate_changed)
        rate.addWidget(self.every_n, 1)
        self.max_fps = QSpinBox()
        self.max_fps.setRange(0, 120)
        self.max_fps.setSpecialValueText("ไม่จำกัด")
        self.max_fps.setPrefix("สูงสุด ")
        self.max_fps.setSuffix(" FPS")
        self.max_fps.setToolTip("จำกัดจำนวนครั้งที่ตรวจจับต่อวินาที (0 = ไม่จำกัด)")
        self.max_fps.valueChanged.connect(self._rate_changed)
        rate.addWidget(self.max_fps, 1)
        lay.addLayout(rate)
        lay.addWidget(hline())
        lay.addWidget(_field("อุปกรณ์ประมวลผล"))
        self.device_combo = QComboBox()
        self.device_combo.addItem("อัตโนมัติ", "auto")
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("CUDA (GPU)", "cuda:0")
        if not self._cuda.get("available"):
            item = self.device_combo.model().item(2)
            item.setEnabled(False)
            self.device_combo.setItemData(2, f"ใช้ไม่ได้: {self._cuda.get('reason', '')}",
                                          Qt.ItemDataRole.ToolTipRole)
        else:
            self.device_combo.setItemText(2, f"CUDA ({self._cuda.get('name')})")
        self.device_combo.activated.connect(self._device_changed)
        lay.addWidget(self.device_combo)
        self.device_note = QLabel("")
        self.device_note.setObjectName("Hint")
        self.device_note.setWordWrap(True)
        lay.addWidget(self.device_note)
        lay.addWidget(hline())
        self.b_classes = _btn("จัดการคลาส…", "tag", None, "ชื่อแสดงผล ตัวกรอง และนำเข้า mapping")
        self.b_classes.clicked.connect(self.open_class_manager)
        lay.addWidget(self.b_classes)
        self.b_info = _btn("ข้อมูลโมเดล…", "cube", None, "รายละเอียดและข้อจำกัดของโมเดลที่เปิดอยู่")
        self.b_info.clicked.connect(self.open_model_info)
        lay.addWidget(self.b_info)
        lay.addWidget(hline())
        sec2 = QLabel("หน่วยความจำภาพที่บันทึก")
        sec2.setObjectName("SectionTitle")
        lay.addWidget(sec2)
        lim = QHBoxLayout()
        lim.setSpacing(6)
        self.max_items = QSpinBox()
        self.max_items.setRange(1, 500)
        self.max_items.setSuffix(" ภาพ")
        self.max_mb = QSpinBox()
        self.max_mb.setRange(16, 8192)
        self.max_mb.setSingleStep(64)
        self.max_mb.setSuffix(" MB")
        self.max_items.valueChanged.connect(self._limits_changed)
        self.max_mb.valueChanged.connect(self._limits_changed)
        lim.addWidget(self.max_items)
        lim.addWidget(self.max_mb)
        lay.addLayout(lim)
        h = QLabel("เมื่อเกินขีดจำกัด ภาพเก่าสุดจะถูกลบออกจากรายการอัตโนมัติ")
        h.setObjectName("Hint")
        h.setWordWrap(True)
        lay.addWidget(h)
        lay.addStretch(1)
        for cb in inner.findChildren(QComboBox):
            cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(8)
        for sp in inner.findChildren(QSpinBox):
            sp.setMinimumWidth(60)
        scroll.setWidget(inner)
        card.body_layout.setContentsMargins(0, 0, 0, 0)
        card.body_layout.addWidget(scroll)
        return card

    def _build_statusbar(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(True)
        self.st_task = QLabel()
        self.st_source = QLabel()
        self.st_device = QLabel()
        self.st_cap = QLabel()
        self.st_cap.setToolTip("Capture FPS: จำนวนเฟรมที่ได้รับจากแหล่งภาพต่อวินาที")
        self.st_inf = QLabel()
        self.st_inf.setToolTip("Inference FPS: จำนวนเฟรมที่ตรวจจับต่อวินาที\n"
                               "เวลาประมวลผล = preprocessing + โมเดล + NMS ต่อภาพ (ไม่รวมการแสดงผล)")
        self.st_count = QLabel()
        self.st_count.setToolTip("จำนวนวัตถุในเฟรมล่าสุด (นับต่อเฟรม ไม่ใช่จำนวนสะสมแบบไม่ซ้ำ — ไม่มี tracking)")
        self.st_clock = QLabel()
        sb.addWidget(self.st_task, 2)
        for w in (self.st_source, self.st_device, self.st_cap, self.st_inf, self.st_count, self.st_clock):
            sb.addPermanentWidget(w)

    def _build_shortcuts(self):
        for seq, fn in (("Ctrl+O", self.open_model_dialog), ("Space", self.capture_snapshot),
                        ("Ctrl+G", self.run_gradcam), ("Ctrl+E", self.export_current),
                        ("F5", self.refresh_cameras), ("Delete", self.delete_current_snapshot)):
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            a.triggered.connect(fn)
            self.addAction(a)

    # ================================================================ settings
    def _apply_settings_to_widgets(self):
        s = self.settings
        self.conf.set_value(s.conf)
        self.iou.set_value(s.iou)
        self._fill_imgsz(None)
        self.every_n.setValue(s.infer_every_n)
        self.max_fps.setValue(int(s.max_infer_fps))
        self.opacity.set_value(s.heatmap_opacity)
        self.max_items.setValue(s.snapshot_max_items)
        self.max_mb.setValue(s.snapshot_max_mb)
        self.sync_cb.setChecked(s.sync_views)
        i = self.device_combo.findData(s.device)
        if i >= 0 and self.device_combo.model().item(i).isEnabled():
            self.device_combo.setCurrentIndex(i)
        self._refresh_model_combo()
        self._update_strip_title()
        self._fill_targets()

    def _fill_imgsz(self, caps):
        self.imgsz_combo.blockSignals(True)
        self.imgsz_combo.clear()
        if caps is not None and not caps.dynamic_input and caps.input_shape:
            v = int(caps.input_shape[-1])
            self.imgsz_combo.addItem(f"{v} (คงที่ตามโมเดล)", v)
            self.imgsz_combo.setEnabled(False)
        else:
            for v in IMGSZ_CHOICES:
                self.imgsz_combo.addItem(f"{v} × {v}", v)
            i = self.imgsz_combo.findData(self.settings.imgsz)
            self.imgsz_combo.setCurrentIndex(i if i >= 0 else IMGSZ_CHOICES.index(640))
            self.imgsz_combo.setEnabled(True)
        self.imgsz_combo.blockSignals(False)

    def _inference_settings(self) -> InferenceSettings:
        return InferenceSettings(conf=self.settings.conf, iou=self.settings.iou,
                                 imgsz=self.settings.imgsz, device=self.settings.device)

    def _settings_changed(self, *_):
        s = self.settings
        s.conf = round(self.conf.value(), 2)
        s.iou = round(self.iou.value(), 2)
        v = self.imgsz_combo.currentData()
        if v:
            s.imgsz = int(v)
        self.worker.set_settings(self._inference_settings())
        if self.source is not None and self.source.kind == "image" and self._last_frame is not None \
                and self.adapter is not None:
            self.worker.submit_job(self._last_frame, ("still", None))

    def _rate_changed(self, *_):
        self.settings.infer_every_n = self.every_n.value()
        self.settings.max_infer_fps = float(self.max_fps.value())
        self.worker.set_rate(self.settings.infer_every_n, self.settings.max_infer_fps)

    def _limits_changed(self, *_):
        self.settings.snapshot_max_items = self.max_items.value()
        self.settings.snapshot_max_mb = self.max_mb.value()
        for s in self.store.set_limits(self.max_items.value(), self.max_mb.value()):
            self._on_evicted(s)
        self._update_strip_title()

    def _device_changed(self, _i):
        dev = self.device_combo.currentData()
        if dev == self.settings.device:
            return
        self.settings.device = dev
        if self.adapter is not None:
            r = QMessageBox.question(self, "อุปกรณ์ประมวลผล",
                                     "ต้องโหลดโมเดลใหม่เพื่อเปลี่ยนอุปกรณ์ประมวลผล — โหลดตอนนี้หรือไม่?")
            if r == QMessageBox.StandardButton.Yes:
                self.load_model(self.adapter.info.identity.path, confirm_trust=False)

    # ================================================================ model
    def _refresh_model_combo(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        cur = self.adapter.info.identity.path if self.adapter else None
        if not cur:
            self.model_combo.addItem("ยังไม่ได้เปิดโมเดล", None)
        for p in self.settings.recent_models:
            self.model_combo.addItem(icon("cube", theme.PURPLE), os.path.basename(p), p)
            self.model_combo.setItemData(self.model_combo.count() - 1, p, Qt.ItemDataRole.ToolTipRole)
        if cur:
            i = self.model_combo.findData(cur)
            if i < 0:
                self.model_combo.insertItem(0, os.path.basename(cur), cur)
                i = 0
            self.model_combo.setCurrentIndex(i)
        self.model_combo.blockSignals(False)

    def _model_combo_activated(self, i):
        p = self.model_combo.itemData(i)
        if not p or (self.adapter and self.adapter.info.identity.path == p):
            return
        if not os.path.isfile(p):
            QMessageBox.warning(self, "เปิดโมเดล", f"ไม่พบไฟล์:\n{p}")
            self.settings.recent_models = [x for x in self.settings.recent_models if x != p]
            self._refresh_model_combo()
            return
        self.load_model(p)

    def open_model_dialog(self):
        if self._busy_loading():
            return
        exts = " ".join(f"*{e}" for e in supported_extensions())
        path, _ = QFileDialog.getOpenFileName(self, "เปิดโมเดล", self.settings.last_open_dir,
                                              f"โมเดลที่รองรับ ({exts})")
        if path:
            self.settings.last_open_dir = os.path.dirname(path)
            self.load_model(path)

    def _busy_loading(self) -> bool:
        if self._load_thread is not None and self._load_thread.isRunning():
            self._set_task("กำลังโหลดโมเดลอยู่ — กรุณารอ")
            return True
        if self._gc_thread is not None and self._gc_thread.isRunning():
            self._set_task("กำลังคำนวณ Grad-CAM — รอให้เสร็จก่อนเปลี่ยนโมเดล")
            return True
        return False

    def _confirm_trust(self, path: str) -> bool:
        try:
            h = file_sha256(path)
        except OSError as e:
            QMessageBox.critical(self, "เปิดโมเดล", f"อ่านไฟล์ไม่ได้: {e}")
            return False
        if h in self.settings.trusted_model_hashes:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("ยืนยันความปลอดภัยของไฟล์ .pt")
        box.setText(f"<b>{os.path.basename(path)}</b><br>SHA-256: {h[:16]}…")
        box.setInformativeText(
            "ไฟล์ .pt ของ PyTorch ถูกโหลดด้วย pickle ซึ่งสามารถรันโค้ด Python ได้ขณะเปิดไฟล์\n"
            "เปิดเฉพาะไฟล์ที่คุณฝึกเองหรือได้จากแหล่งที่เชื่อถือได้เท่านั้น\n"
            "โปรแกรมจะไม่ติดตั้งแพ็กเกจหรือรันสคริปต์อื่นที่มากับโมเดล")
        cb = QCheckBox("เชื่อถือไฟล์นี้ (จำ SHA-256 ไม่ต้องถามอีก)")
        box.setCheckBox(cb)
        ok = box.addButton("เปิดไฟล์", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("ยกเลิก", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not ok:
            return False
        if cb.isChecked():
            self.settings.trusted_model_hashes = (self.settings.trusted_model_hashes + [h])[-200:]
        return True

    def load_model(self, path: str, device: str | None = None, confirm_trust: bool = True):
        if self._busy_loading():
            return
        if confirm_trust and path.lower().endswith(".pt") and not self._confirm_trust(path):
            return
        self.worker.pause("กำลังโหลดโมเดล")
        old = self.adapter
        self.worker.set_adapter(None)        # waits for a running inference to finish
        self.adapter = None
        self.class_view = None
        self._live_pair = None
        if old is not None:
            old.close()                      # release previous model resources
        self._fill_targets()
        self._set_task(f"กำลังโหลดโมเดล {os.path.basename(path)} …")
        self.header_meta.setText(f"กำลังโหลด {os.path.basename(path)} …")
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        self._pending_model = path
        self._load_thread = ModelLoadThread(path, device or self.settings.device, self)
        self._load_thread.loaded.connect(self._model_loaded)
        self._load_thread.failed.connect(self._model_failed)
        self._load_thread.start()
        self._update_states()

    def _model_loaded(self, adapter):
        QApplication.restoreOverrideCursor()
        self.adapter = adapter
        info = adapter.info
        self._apply_class_view()
        self._fill_imgsz(info.caps)
        self._settings_changed()
        self.worker.set_adapter(adapter)
        self.worker.resume()
        self.settings.add_recent_model(info.identity.path)
        self._refresh_model_combo()
        self._fill_layers()
        gc = "Grad-CAM พร้อม" if info.caps.grad_cam else "Grad-CAM ไม่รองรับ"
        self.header_meta.setText(f"โมเดล: {info.identity.name} • {info.device.upper()} • {gc}")
        reg = self.class_view.registry
        self.model_summary.setText(
            f"<b>{info.identity.name}</b> ({info.identity.adapter})<br>"
            f"task: {info.caps.task} • คลาส {reg.count} • {info.device}<br>"
            f"{'Grad-CAM: พร้อมใช้งาน' if info.caps.grad_cam else info.gradcam_status}")
        self.device_note.setText(f"กำลังใช้: {info.device}")
        self._set_task(f"โหลดโมเดลแล้ว: {info.identity.name} (คลาส {reg.count}, {info.device})")
        warn = [*info.caps.limitations, *reg.notes]
        if warn:
            self._set_task("โหลดโมเดลแล้ว — มีข้อควรทราบ: " + warn[0])
        if self.source is not None and self.source.kind == "image" and self._last_frame is not None:
            self.worker.submit_job(self._last_frame, ("still", None))
        self._show_snapshot()
        self._update_states()
        self.modelLoaded.emit(True)

    def _model_failed(self, msg: str, kind: str):
        QApplication.restoreOverrideCursor()
        path = self._pending_model
        self.worker.resume()
        self.header_meta.setText("ยังไม่ได้เปิดโมเดล")
        self._refresh_model_combo()
        self._update_states()
        if kind == "device":
            r = QMessageBox.question(self, "อุปกรณ์ประมวลผล", f"{msg}\n\nโหลดโมเดลบน CPU แทนหรือไม่?")
            if r == QMessageBox.StandardButton.Yes:
                self.settings.device = "cpu"
                self.device_combo.setCurrentIndex(self.device_combo.findData("cpu"))
                self.load_model(path, "cpu", confirm_trust=False)
                return
        self._set_task("⚠ เปิดโมเดลไม่สำเร็จ")
        QMessageBox.critical(self, "เปิดโมเดลไม่สำเร็จ", msg)
        self.modelLoaded.emit(False)

    def _apply_class_view(self):
        info = self.adapter.info
        h = info.identity.sha256
        reg = info.classes
        imp = self.names_store.imported_mapping(h)
        if imp:
            names, src_file = imp
            try:
                compare_mapping(reg.names, names, self.adapter.output_class_count())
                reg = ClassRegistry(names, SOURCE_FILE, self.adapter.output_class_count() is not None,
                                    source_detail=src_file)
                self.adapter.set_class_registry(reg)
            except ClassMappingError as e:
                self._set_task(f"⚠ mapping ที่บันทึกไว้ใช้กับโมเดลนี้ไม่ได้: {e}")
        self.class_view = ClassView(reg, self.names_store.display_names(h), self.names_store.hidden(h))

    def _fill_layers(self):
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        eng = self.adapter.gradcam_engine() if self.adapter else None
        if eng is None:
            reason = self.adapter.info.gradcam_status if self.adapter else "ยังไม่ได้เปิดโมเดล"
            self.layer_combo.addItem("ไม่รองรับ", None)
            self.layer_combo.setToolTip(reason)
            self.layer_combo.setEnabled(False)
        else:
            for key, label in eng.layer_options():
                self.layer_combo.addItem(label, key)
            self.layer_combo.setToolTip("อัตโนมัติ = feature map ของ head (P3/P4/P5) ที่ anchor ของวัตถุอยู่")
            self.layer_combo.setEnabled(True)
        self.layer_combo.blockSignals(False)

    # ================================================================ classes
    def open_class_manager(self):
        if self.adapter is None:
            return
        info = self.adapter.info
        dlg = ClassManagerDialog(self.class_view.registry, self.class_view.display,
                                 self.class_view.hidden, self.adapter.output_class_count(),
                                 info.identity.name, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        h = info.identity.sha256
        if dlg.new_registry is not None:
            self.names_store.set_imported_mapping(h, dlg.new_registry.names, dlg.mapping_file)
            self.adapter.set_class_registry(dlg.new_registry)
        self.names_store.set_display_names(h, dlg.display_names())
        self.names_store.set_hidden(h, dlg.hidden_ids())
        self._apply_class_view()
        # same model -> update display names/filter of its snapshots (original names stay frozen)
        for s in self.store.all():
            if s.result.model.sha256 == h:
                s.display_names = dict(self.class_view.display)
                s.hidden_classes = set(self.class_view.hidden)
                if dlg.new_registry is not None:
                    s.class_names = dict(dlg.new_registry.names)
                    s.class_source = dlg.new_registry.source
        self._show_snapshot()
        self._set_task("บันทึกการตั้งค่าคลาสแล้ว")

    def open_model_info(self):
        if self.adapter is not None:
            ModelInfoDialog(self.adapter.info, self).exec()

    def _live_label(self, d):
        cv = self.class_view
        name = cv.label(d.class_id) if cv else str(d.class_id)
        return f"{name} {format_confidence(d.confidence)}"

    # ================================================================ sources
    def _mode_changed(self, _i):
        self.mode = self.mode_combo.currentData()
        self.src_stack.setCurrentIndex(0 if self.mode == MODE_CAMERA else 1)
        self.file_path = ""
        self.file_edit.clear()
        self.file_edit.setPlaceholderText({MODE_VIDEO: "เลือกไฟล์วิดีโอ…", MODE_IMAGE: "เลือกไฟล์ภาพ…",
                                           MODE_FOLDER: "เลือกโฟลเดอร์ภาพ…"}.get(self.mode, ""))
        self._update_states()

    def browse_source(self):
        start = self.settings.last_open_dir
        if self.mode == MODE_VIDEO:
            p, _ = QFileDialog.getOpenFileName(self, "เลือกวิดีโอ", start,
                                               "วิดีโอ (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v);;ทุกไฟล์ (*)")
        elif self.mode == MODE_IMAGE:
            p, _ = QFileDialog.getOpenFileName(self, "เลือกภาพ", start, "ภาพ (*.jpg *.jpeg *.png *.bmp)")
        else:
            p = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ภาพ", start)
        if p:
            self.set_file_source(p)

    def set_file_source(self, path: str):
        self.file_path = path
        self.file_edit.setText(path)
        self.settings.last_open_dir = path if os.path.isdir(path) else os.path.dirname(path)
        self._update_states()

    def refresh_cameras(self, initial: bool = False):
        self.cam_combo.blockSignals(True)
        prev = self.cam_combo.currentData()
        self.cam_combo.clear()
        try:
            from ..sources.qt_camera import list_qt_cameras
            cams = list_qt_cameras()
            err = ""
        except Exception as e:
            cams, err = [], str(e)
        self.cam_combo.addItem("— เลือกกล้อง —", None)
        for c in cams:
            self.cam_combo.addItem(icon("camera", theme.TEXT), c.name,
                                   {"kind": "qt-camera", "ident": c.ident, "name": c.name, "detail": c.detail})
            self.cam_combo.setItemData(self.cam_combo.count() - 1, c.detail, Qt.ItemDataRole.ToolTipRole)
        for ip in self.settings.ip_cameras:
            self.cam_combo.addItem(icon("link", theme.TEXT), f"{ip.get('name')} (RTSP)", dict(ip))
        pref = self.settings.preferred_camera or {}
        if pref.get("kind") == "opencv-index":
            self.cam_combo.addItem(icon("settings", theme.TEXT), pref.get("name", "OpenCV"), dict(pref))
        self.cam_combo.addItem(icon("settings", theme.TEXT), "เลือก/ตั้งค่ากล้อง…", "__dialog__")
        target = prev if (prev and not initial) else pref
        idx = 0
        if target:
            for i in range(self.cam_combo.count()):
                d = self.cam_combo.itemData(i)
                if isinstance(d, dict) and d.get("kind") == target.get("kind") and \
                        (d.get("ident") == target.get("ident") if d.get("kind") == "qt-camera"
                         else d.get("name") == target.get("name")):
                    idx = i
                    break
            else:
                if target.get("kind") == "qt-camera":
                    self._set_task(f"⚠ ไม่พบกล้องที่เลือกไว้ '{target.get('name')}' — กรุณาเลือกกล้องใหม่ "
                                   "(ไม่สลับกล้องอัตโนมัติ)")
        self.cam_combo.setCurrentIndex(idx)
        self.cam_combo.blockSignals(False)
        if err:
            self._set_task(f"⚠ ค้นหากล้องไม่ได้: {err}")
        elif not initial:
            self._set_task(f"พบกล้อง {len(cams)} อุปกรณ์")
        self._update_states()

    def _camera_combo_activated(self, i):
        d = self.cam_combo.itemData(i)
        if d == "__dialog__":
            self.cam_combo.setCurrentIndex(0)
            self.open_camera_dialog()
        elif isinstance(d, dict):
            self.settings.preferred_camera = {k: v for k, v in d.items() if k != "password_session"}
        self._update_states()

    def open_camera_dialog(self):
        was_running = self.source is not None and self.source.kind in ("qt-camera", "opencv-index")
        if was_running:
            self.stop_source()          # release device so the dialog can test it
        dlg = CameraDialog(self.settings, self.settings.preferred_camera, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.choice:
            ch = dlg.choice
            self.settings.preferred_camera = {k: v for k, v in ch.items() if k != "password_session"}
            self.refresh_cameras()
            for j in range(self.cam_combo.count()):
                d = self.cam_combo.itemData(j)
                if isinstance(d, dict) and d.get("name") == ch.get("name") and d.get("kind") == ch.get("kind"):
                    if ch.get("password_session"):
                        d = dict(d, password_session=ch["password_session"])
                        self.cam_combo.setItemData(j, d)
                    if ch.get("fmt"):
                        self.cam_combo.setItemData(j, dict(d, fmt=ch["fmt"]))
                    self.cam_combo.setCurrentIndex(j)
                    break
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(MODE_CAMERA))
        self._update_states()

    def start_source(self):
        self.stop_source()
        try:
            if self.mode == MODE_CAMERA:
                ch = self.cam_combo.currentData()
                if not isinstance(ch, dict):
                    self.open_camera_dialog()
                    ch = self.cam_combo.currentData()
                    if not isinstance(ch, dict):
                        return
                src = make_source(ch, self)
            elif self.mode == MODE_VIDEO:
                if not self.file_path:
                    self.browse_source()
                if not self.file_path:
                    return
                src = OpenCVSource("video", self.file_path, os.path.basename(self.file_path))
            else:
                if not self.file_path:
                    self.browse_source()
                if not self.file_path:
                    return
                src = ImageSource.from_path(self.file_path)
        except Exception as e:
            QMessageBox.warning(self, "แหล่งภาพ", str(e))
            return
        self.source = src
        self.source_bridge = SourceBridge(self)
        self.source_bridge.attach(src)
        self.source_bridge.frame.connect(self._on_frame)
        self.source_bridge.status.connect(self._on_source_status)
        self.source_bridge.error.connect(self._on_source_error)
        self.source_bridge.stopped.connect(self._on_source_stopped)
        self._live_pair = None
        self._source_state = "กำลังเชื่อมต่อ"
        self.live_view.set_message("กำลังเปิดแหล่งภาพ …")
        self.b_pause.setChecked(False)
        src.start()
        self._update_states()

    def stop_source(self):
        src = self.source
        if src is None:
            return
        self.source = None
        if self.source_bridge is not None:
            try:
                self.source_bridge.frame.disconnect(self._on_frame)
            except (RuntimeError, TypeError):
                pass
        src.on_frame = None
        src.stop()
        self.worker.slot.clear()
        self._source_state = "หยุดแล้ว"
        self._set_dot(False)
        self._update_states()

    def _toggle_pause(self, on):
        if self.source is not None and self.source.supports_pause():
            self.source.set_paused(on)

    def _step_image(self, d):
        if isinstance(self.source, ImageSource):
            self.source.step(d)

    def _on_source_status(self, msg):
        self._source_state = redact(msg)
        self._set_task(redact(msg))

    def _on_source_error(self, msg):
        self._source_state = "ขัดข้อง"
        self.live_view.set_message(redact(msg))
        self._set_task("⚠ " + redact(msg))

    def _on_source_stopped(self):
        if self.source is not None and not self.source.running and self.source.kind != "image":
            self.source = None
            self._set_dot(False)
        self._update_states()

    def _on_frame(self, pkt: FramePacket):
        if self.source is None:
            return
        self._last_frame = pkt
        self._set_dot(True)
        detecting = self.adapter is not None and not self.worker.paused
        if self.source.kind == "image":
            if self.adapter is not None:
                self.worker.submit_job(pkt, ("still", None))
        elif detecting:
            self.worker.submit_frame(pkt)
        # without detection: show raw frames (throttled to ~30 FPS)
        if not detecting or self.source.kind == "image":
            now = time.perf_counter()
            if now - self._last_preview_t > 1 / 30:
                self._last_preview_t = now
                self.live_view.set_frame(pkt.image)
                if self._live_dialog is not None:
                    self._live_dialog.set_frame(pkt.image)
        self._update_states_light()

    # ================================================================ results
    def _on_result(self, pkt, res, kind, tag):
        if self.adapter is None or res.model.sha256 != self.adapter.info.identity.sha256:
            log.info("discarding result from previous model")
            return
        if isinstance(tag, tuple) and tag[0] == "snapshot":
            self._add_snapshot(pkt, res)
            return
        self._live_pair = (pkt, res)
        cv = self.class_view
        dets = [d for d in res.detections if cv is None or cv.visible(d.class_id)]
        self._frame_count = (len(dets), len(res.detections))
        self.live_view.set_frame(pkt.image, dets, self._live_label)
        if self._live_dialog is not None:
            self._live_dialog.set_frame(pkt.image, dets, self._live_label)

    def capture_snapshot(self):
        if self.adapter is None:
            self._set_task("เปิดโมเดลก่อนจับภาพ")
            return
        pkt = self._last_frame
        if pkt is None:
            self._set_task("ยังไม่มีภาพจากแหล่งภาพ")
            return
        lp = self._live_pair
        settings_now = self.worker.settings()
        if lp is not None and lp[0].frame_id == pkt.frame_id and lp[1].settings == settings_now:
            self._add_snapshot(lp[0], lp[1])          # exact frame/result pair already available
        else:
            copy = FramePacket(pkt.frame_id, pkt.timestamp, pkt.image.copy(), pkt.source_label)
            self.worker.submit_job(copy, ("snapshot", None))
            self._set_task("กำลังตรวจจับภาพที่จับไว้ …")

    def _add_snapshot(self, pkt, res):
        cv = self.class_view
        snap = Snapshot(self.store.next_index(), pkt.image.copy(), res, dict(cv.registry.names),
                        cv.registry.source, dict(cv.display), set(cv.hidden),
                        pkt.source_label or (self.source.label if self.source else ""))
        for ev in self.store.add(snap):
            self._on_evicted(ev)
        self.strip.add_snapshot(snap)
        self.strip.select_index(snap.index)
        self._update_strip_title()
        self._set_task(f"บันทึกภาพที่ {snap.index:02d} — พบ {len(res.detections)} วัตถุ")
        self.snapshotAdded.emit(snap.index)

    def _on_evicted(self, snap):
        self.strip.remove_index(snap.index)
        if self.current_snap is snap:
            self.current_snap = None
            self._show_snapshot()
        self._set_task(f"ลบภาพที่ {snap.index:02d} ออกอัตโนมัติ (เกินขีดจำกัดหน่วยความจำ)")

    def _update_strip_title(self):
        n = len(self.store)
        self.strip_title.setText(f"ภาพที่บันทึก ({n})")
        self.strip_info.setText(f"  ใช้ {self.store.total_bytes / 2**20:.0f}/{self.store.max_mb} MB • "
                                f"สูงสุด {self.store.max_items} ภาพ")

    def _strip_selected(self):
        idx = self.strip.current_index()
        self.current_snap = self.store.get(idx) if idx is not None else None
        self.selected_det = None
        if self.current_snap is not None and self.current_snap.result.detections:
            vis = self.current_snap.visible_detections() or self.current_snap.result.detections
            self.selected_det = max(vis, key=lambda d: d.confidence).det_id
        self._show_snapshot()

    def delete_current_snapshot(self):
        idx = self.strip.current_index()
        if idx is None:
            return
        self.store.remove(idx)
        self.strip.remove_index(idx)
        self._update_strip_title()
        if self.strip.count() == 0:
            self.current_snap = None
            self._show_snapshot()

    def _strip_menu(self, pos):
        it = self.strip.itemAt(pos)
        m = QMenu(self)
        if it is not None:
            self.strip.setCurrentItem(it)
            m.addAction("เปิดดูภาพ", self.open_snapshot_viewer)
            m.addAction("ส่งออก…", self.export_current)
            m.addAction("ลบออกจากรายการ", self.delete_current_snapshot)
            m.addSeparator()
        m.addAction("ล้างทั้งหมด", self.clear_snapshots)
        m.exec(self.strip.mapToGlobal(pos))

    def clear_snapshots(self):
        if len(self.store) and QMessageBox.question(self, "ล้างรายการ", "ลบภาพที่บันทึกทั้งหมดออกจากรายการ?") \
                == QMessageBox.StandardButton.Yes:
            self.store.clear()
            self.strip.clear()
            self.current_snap = None
            self._show_snapshot()
            self._update_strip_title()

    # ================================================================ display
    def _det_by_id(self, det_id):
        s = self.current_snap
        if s is None or det_id is None:
            return None
        for d in s.result.detections:
            if d.det_id == det_id:
                return d
        return None

    def _show_snapshot(self):
        s = self.current_snap
        if s is None:
            self.det_view.set_placeholder("ยังไม่มีภาพที่บันทึก — กด 'เริ่ม' แล้ว 'จับภาพ'")
            self.det_card.meta.setText("")
            self.table.set_detections([], str)
            self.filter_note.setText("")
            self.detail.clear()
            self._fill_targets()
            self._show_gradcam()
            self._update_states()
            return
        dt = _dt.datetime.fromtimestamp(s.result.timestamp)
        meta = f"ภาพที่ {s.index:02d}   {dt:%H:%M:%S}"
        for c in (self.det_card, self.gc_card):
            c.meta.setText(meta)
            c.meta.setToolTip(f"ภาพที่ {s.index:02d} • {dt:%Y-%m-%d %H:%M:%S} • frame {s.result.frame_id}")
        self.det_view.set_image(s.image, keep_view=True)
        vis = s.visible_detections()
        hidden_n = len(s.result.detections) - len(vis)
        lab = lambda d: f"{s.label(d.class_id)} {format_confidence(d.confidence)}"  # noqa: E731
        self.det_view.set_boxes(vis, lab, self.selected_det)
        self.table.set_detections(vis, s.label, self.selected_det)
        notes = []
        if hidden_n:
            notes.append(f"ซ่อน {hidden_n} รายการตามตัวกรองคลาส")
        if self.adapter is not None and s.result.model.sha256 != self.adapter.info.identity.sha256:
            notes.append(f"ภาพนี้มาจากโมเดล {s.result.model.name} ({s.result.model.short_hash}) "
                         "ไม่ใช่โมเดลปัจจุบัน")
        notes.append(f"conf {format_confidence(s.result.settings.conf)} • IoU "
                     f"{format_confidence(s.result.settings.iou)} • input {s.result.settings.imgsz} • "
                     f"{s.result.device} • {s.result.inference_ms:.0f} ms")
        self.filter_note.setText("  •  ".join(notes))
        d = self._det_by_id(self.selected_det)
        if d is not None:
            self.detail.show_detection(s, d)
            self.detail_card.title.setText(f"ตัวอย่างวัตถุที่เลือก: {s.label(d.class_id)}")
            self.gc_card.title.setText(f"วิเคราะห์ Grad-CAM • วัตถุที่เลือก: {s.label(d.class_id)}")
        else:
            self.detail.clear("ไม่มีวัตถุที่ตรวจพบ" if not vis else "เลือกวัตถุจากตาราง")
            self.detail_card.title.setText("ตัวอย่างวัตถุที่เลือก: -")
            self.gc_card.title.setText("วิเคราะห์ Grad-CAM • วัตถุที่เลือก: -")
        self._fill_targets()
        self._show_gradcam()
        self._update_states()

    def _fill_targets(self):
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        s = self.current_snap
        if s is not None:
            for d in s.visible_detections():
                self.target_combo.addItem(icon("search", theme.MUTED),
                                          f"#{d.det_id + 1} • {s.label(d.class_id)} ({d.class_id}) • "
                                          f"{format_confidence(d.confidence)}", d.det_id)
            i = self.target_combo.findData(self.selected_det)
            self.target_combo.setCurrentIndex(i)
        if self.target_combo.count() == 0:
            self.target_combo.addItem("— ไม่มีวัตถุ —", None)
        self.target_combo.blockSignals(False)

    def select_detection(self, det_id):
        if det_id is None or self._det_by_id(det_id) is None:
            return
        self.selected_det = det_id
        self._show_snapshot()

    def _sync(self, src: ImageView, dst: ImageView):
        if self.sync_cb.isChecked() and dst.has_image() and src.has_image():
            dst.copy_view_from(src)

    def _show_gradcam(self, render_only: bool = False):
        s = self.current_snap
        d = self._det_by_id(self.selected_det)
        if self._gc_thread is not None and self._gc_thread.isRunning():
            return
        if s is None or d is None:
            self.gc_view.set_placeholder("เลือกวัตถุจากภาพที่จับไว้ แล้วกด 'วิเคราะห์'")
            self._set_gc_note("")
            return
        g = s.gradcam
        layer = self.layer_combo.currentData() or "auto"
        method = self.method_combo.currentData() or "gradcam"
        if g is None or g.det_id != d.det_id or g.layer_key != layer or g.method != method:
            if self.adapter is None or not self.adapter.info.caps.grad_cam:
                reason = self.adapter.info.gradcam_status if self.adapter else "ยังไม่ได้เปิดโมเดล"
                self.gc_view.set_placeholder(f"Grad-CAM ใช้ไม่ได้กับโมเดลนี้\n{reason}")
            else:
                self.gc_view.set_placeholder(
                    f"ยังไม่ได้วิเคราะห์วัตถุ #{d.det_id + 1} ({s.label(d.class_id)})\n"
                    "กด 'วิเคราะห์' เพื่อคำนวณ Grad-CAM จากภาพที่จับไว้นี้")
            self._set_gc_note(GRADCAM_NOTICE)
            return
        over = overlay_heatmap(s.image, g.heatmap, self.opacity.value())
        self.gc_view.set_image(over, keep_view=True)
        lab = lambda x: f"{s.label(x.class_id)} {format_confidence(x.confidence)}"  # noqa: E731
        self.gc_view.set_boxes([d], lab, d.det_id)
        if self.sync_cb.isChecked():
            self.gc_view.copy_view_from(self.det_view)
        dd = g.details
        txt = (f"{'HiResCAM' if g.method == 'hirescam' else 'Grad-CAM'} • ชั้น {g.layer_name} • target ก่อน NMS: anchor {dd.get('matched_anchor_index')} "
               f"({dd.get('matched_level')}) IoU {dd.get('match_iou', 0):.3f} • score "
               f"{dd.get('pre_nms_score', 0):.3f} • {dd.get('device')} {dd.get('elapsed_ms', 0):.0f} ms")
        if dd.get("match_warning"):
            txt += f"\n⚠ {dd['match_warning']}"
        if dd.get("placement_note"):
            txt += f"\n{dd['placement_note']}"
        self._set_gc_note(txt)

    def _set_gc_note(self, txt: str):
        first = txt.split("\n")[0]
        if "\n" in txt:
            first = "⚠ " + first if "⚠" in txt else first
        self.gc_note.setText(first)
        self.gc_note.setToolTip(txt)

    # ================================================================ Grad-CAM
    def run_gradcam(self):
        s = self.current_snap
        d = self._det_by_id(self.selected_det)
        if s is None or d is None or self.adapter is None:
            self._set_task("เลือกภาพที่จับไว้และวัตถุก่อนวิเคราะห์ Grad-CAM")
            return
        if self._gc_thread is not None and self._gc_thread.isRunning():
            return
        if s.result.model.sha256 != self.adapter.info.identity.sha256:
            QMessageBox.information(self, "Grad-CAM", "ภาพนี้ตรวจด้วยโมเดลอื่น — เปิดโมเดลเดิมก่อน "
                                    f"({s.result.model.name}) เพื่อให้ Grad-CAM ตรงกับผลตรวจ")
            return
        eng = self.adapter.gradcam_engine()
        if eng is None:
            QMessageBox.information(self, "Grad-CAM", self.adapter.info.gradcam_status)
            return
        layer = self.layer_combo.currentData() or "auto"
        job = {"snap": s.index, "det": d, "image": s.image, "imgsz": s.result.settings.imgsz,
               "layer": layer, "method": self.method_combo.currentData() or "gradcam"}
        self.gc_view.set_placeholder(f"กำลังคำนวณ Grad-CAM สำหรับวัตถุ #{d.det_id + 1} "
                                     f"({s.label(d.class_id)}) …\nพักการตรวจจับสดชั่วคราว (ภาพสดยังแสดงอยู่)")
        self._set_task("กำลังคำนวณ Grad-CAM — พักการตรวจจับสดชั่วคราว")
        self.worker.pause("Grad-CAM")          # paused synchronously; the thread resumes it
        self._gc_thread = GradCamThread(eng, self.worker, job, self)
        self._gc_thread.done.connect(self._gradcam_done)
        self._gc_thread.failed.connect(self._gradcam_failed)
        self._gc_thread.finished.connect(self._update_states)
        self._gc_thread.start()
        self._update_states()

    def _gradcam_done(self, out, job):
        snap = self.store.get(job["snap"])
        if snap is not None:
            d = job["det"]
            snap.gradcam = GradCamRecord(d.det_id, d.class_id, d.confidence, d.box, job["layer"],
                                         out.layer_name, out.heatmap, out.details, job["method"])
        self._set_task(f"Grad-CAM เสร็จ ({out.details.get('elapsed_ms', 0):.0f} ms) — กลับมาตรวจจับสดแล้ว")
        QTimer.singleShot(0, self._after_gradcam)
        self.gradcamFinished.emit(True)

    def _after_gradcam(self):
        self._show_gradcam()
        self._update_states()

    def _gradcam_failed(self, msg, job):
        self.gc_view.set_placeholder(f"Grad-CAM ไม่สำเร็จ\n{msg}", error=True)
        self._set_gc_note("ไม่มีการสร้าง Heatmap แทนผลจริง")
        self._set_task("⚠ " + msg)
        self.gradcamFinished.emit(False)

    # ================================================================ export / viewers
    def export_current(self):
        s = self.current_snap
        if s is None:
            self._set_task("เลือกภาพที่บันทึกก่อนส่งออก")
            return
        dlg = ExportDialog(self.settings.last_export_dir, s.gradcam is not None, bool(s.hidden_classes), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        out = dlg.path.text().strip()
        self.settings.last_export_dir = out
        self.export_snapshot_to(s, out, dlg.options(self.opacity.value()))

    def export_snapshot_to(self, s, out_dir, opts):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            files = export_snapshot(s, out_dir, opts, render_fn=render_detections_qt)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "ส่งออกไม่สำเร็จ", str(e))
            return []
        QApplication.restoreOverrideCursor()
        folder = os.path.dirname(files[0]) if files else out_dir
        self._set_task(f"ส่งออก {len(files)} ไฟล์ไปที่ {folder}")
        return files

    def open_snapshot_viewer(self):
        s = self.current_snap
        if s is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"ภาพที่ {s.index:02d} — {s.source_label}")
        dlg.resize(1100, 760)
        lay = QVBoxLayout(dlg)
        v = ImageView()
        lay.addWidget(v)
        v.set_image(s.image)
        lab = lambda d: f"{s.label(d.class_id)} {format_confidence(d.confidence)}"  # noqa: E731
        v.set_boxes(s.visible_detections(), lab, self.selected_det)
        dlg.show()

    def open_live_viewer(self):
        if self._live_dialog is not None:
            self._live_dialog.raise_()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("ภาพสด (ขยาย)")
        dlg.resize(1024, 640)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        view = LiveView()
        lay.addWidget(view)
        self._live_dialog = view
        dlg.finished.connect(lambda *_: setattr(self, "_live_dialog", None))
        dlg.show()

    # ================================================================ state / status
    def _set_task(self, text: str):
        self._task = text
        self.st_task.setText(text)
        log.info("status: %s", redact(text))

    def _update_states_light(self):
        running = self.source is not None
        can_capture = self.adapter is not None and self._last_frame is not None
        if self.b_stop.isEnabled() != running or self.b_capture.isEnabled() != can_capture:
            self._update_states()

    def _update_states(self, *_):
        loading = self._load_thread is not None and self._load_thread.isRunning()
        gc_running = self._gc_thread is not None and self._gc_thread.isRunning()
        running = self.source is not None
        has_model = self.adapter is not None
        if self.mode == MODE_CAMERA:
            have_src = isinstance(self.cam_combo.currentData(), dict) or self.cam_combo.count() > 0
        else:
            have_src = True
        self.b_open.setEnabled(not loading and not gc_running)
        self.model_combo.setEnabled(not loading and not gc_running)
        self.b_start.setEnabled(have_src and not running)
        self.b_stop.setEnabled(running)
        self.b_pause.setEnabled(running and self.source.supports_pause())
        is_folder = isinstance(self.source, ImageSource) and len(self.source.paths) > 1
        self.b_prev_img.setVisible(is_folder)
        self.b_next_img.setVisible(is_folder)
        self.b_capture.setEnabled(has_model and self._last_frame is not None and not loading)
        if not has_model:
            self.b_capture.setToolTip("เปิดโมเดลก่อนจับภาพ")
        else:
            self.b_capture.setToolTip("บันทึก snapshot พร้อมผลตรวจจับ (Space)")
        s = self.current_snap
        d = self._det_by_id(self.selected_det)
        same_model = has_model and s is not None and s.result.model.sha256 == self.adapter.info.identity.sha256
        can_gc = bool(has_model and self.adapter.info.caps.grad_cam and d is not None and same_model
                      and not gc_running and not loading)
        self.b_gradcam.setEnabled(can_gc)
        if has_model and not self.adapter.info.caps.grad_cam:
            self.b_gradcam.setToolTip(self.adapter.info.gradcam_status)
        elif s is not None and has_model and not same_model:
            self.b_gradcam.setToolTip("ภาพนี้มาจากโมเดลอื่น")
        else:
            self.b_gradcam.setToolTip("วิเคราะห์ Grad-CAM ของวัตถุที่เลือก (Ctrl+G)")
        self.b_export.setEnabled(s is not None and not gc_running)
        self.b_classes.setEnabled(has_model and not loading)
        self.b_info.setEnabled(has_model)
        self.layer_combo.setEnabled(has_model and self.adapter.info.caps.grad_cam and not gc_running)
        self.method_combo.setEnabled(has_model and self.adapter.info.caps.grad_cam and not gc_running)
        self.target_combo.setEnabled(s is not None and not gc_running)
        self.mode_combo.setEnabled(not running)
        self.src_stack.setEnabled(not running)
        if self.worker.paused and self.worker.pause_reason:
            self.live_badge.setText(f"พักตรวจจับ ({self.worker.pause_reason})")
            self.live_badge.show()
        else:
            self.live_badge.hide()

    def _update_status(self):
        src = self.source
        if src is not None:
            res = src.actual_resolution
            rtxt = f" ({res[0]} × {res[1]})" if res else ""
            pos = ""
            if isinstance(src, ImageSource):
                pos = f" [{src.position_text()}]"
            self.live_meta.setText(f"{redact(src.label)}{rtxt}{pos}")
            self.st_source.setText(f"แหล่งภาพ: {redact(src.label)} • {self._source_state}")
            self.st_cap.setText(f"Capture {src.capture_fps.fps:.1f} FPS")
        else:
            self.st_source.setText("แหล่งภาพ: -")
            self.st_cap.setText("Capture - FPS")
            if self._last_frame is None:
                self.live_meta.setText("—")
        dev = self.adapter.info.device if self.adapter else "-"
        self.st_device.setText(f"Device: {dev}")
        if self.worker.paused:
            self.st_inf.setText(f"Inference: พัก ({self.worker.pause_reason})")
        else:
            self.st_inf.setText(f"Inference {self.worker.infer_fps.fps:.1f} FPS • {self.worker.last_ms:.0f} ms/ภาพ")
        if self._frame_count is not None:
            shown, total = self._frame_count
            self.st_count.setText(f"วัตถุในเฟรม: {shown}" + (f" (จาก {total})" if total != shown else ""))
        else:
            self.st_count.setText("วัตถุในเฟรม: -")
        self.st_clock.setText(_dt.datetime.now().strftime("%H:%M:%S"))
        self._update_strip_title()
        self._update_states()

    # ================================================================ shutdown
    def closeEvent(self, e):
        self.stop_source()
        if self._gc_thread is not None:
            self._gc_thread.wait(30000)
        if self._load_thread is not None:
            self._load_thread.wait(30000)
        self.worker.stop()
        if self.adapter is not None:
            self.adapter.close()
        self.settings.heatmap_opacity = round(self.opacity.value(), 2)
        self.settings.sync_views = self.sync_cb.isChecked()
        try:
            self.settings.save()
        except OSError:
            log.exception("could not save settings")
        super().closeEvent(e)
