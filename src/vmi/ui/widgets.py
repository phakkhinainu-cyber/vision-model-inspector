"""Reusable widgets for the main window."""
from __future__ import annotations

import datetime as _dt

import cv2
import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QDoubleSpinBox, QFrame,
                               QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QRadioButton, QSizePolicy, QSlider,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from ..core.imageops import class_color_rgb
from ..core.types import format_confidence
from . import theme
from .icons import icon


# ---------------------------------------------------------------- conversions
def bgr_to_qimage(img: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def qimage_to_bgr(q: QImage) -> np.ndarray:
    q = q.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = q.width(), q.height(), q.bytesPerLine()
    arr = np.frombuffer(q.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)[:, : w * 3]
    return cv2.cvtColor(arr.reshape(h, w, 3), cv2.COLOR_RGB2BGR)


def bgr_to_pixmap(img: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(bgr_to_qimage(img))


def label_font(px: float) -> QFont:
    f = QFont(theme.FONT_FAMILY_ACTIVE if hasattr(theme, "FONT_FAMILY_ACTIVE") else theme.FONT_FAMILY)
    f.setPixelSize(max(9, int(px)))
    f.setWeight(QFont.Weight.DemiBold)
    return f


def paint_detection(p: QPainter, rect: QRectF, color: QColor, text: str, line_w: float,
                    font_px: float, selected: bool = False):
    pen = QPen(color, line_w * (1.6 if selected else 1.0))
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(rect)
    f = label_font(font_px)
    p.setFont(f)
    fm = QFontMetricsF(f)
    tw = fm.horizontalAdvance(text) + font_px * 0.8
    th = fm.height() + font_px * 0.15
    y = rect.top() - th if rect.top() - th >= 0 else rect.top()
    bg = QRectF(rect.left() - line_w / 2, y, tw, th)
    p.fillRect(bg, color)
    p.setPen(QColor("white"))
    p.drawText(bg, Qt.AlignmentFlag.AlignCenter, text)


def render_detections_qt(image_bgr: np.ndarray, detections, label_fn, selected_id=None) -> np.ndarray:
    """Draw boxes + Thai labels with QPainter (correct Thai shaping)."""
    q = bgr_to_qimage(image_bgr)
    p = QPainter(q)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    s = max(image_bgr.shape[:2]) / 1000.0
    for d in detections:
        x1, y1, x2, y2 = d.box
        paint_detection(p, QRectF(x1, y1, x2 - x1, y2 - y1), QColor(*class_color_rgb(d.class_id)),
                        label_fn(d), max(2.0, 3 * s), max(12.0, 18 * s), d.det_id == selected_id)
    p.end()
    return qimage_to_bgr(q)


# ---------------------------------------------------------------- card
class Card(QFrame):
    def __init__(self, title: str, accent: bool = False, meta: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("CardAccent" if accent else "Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        self.header = QFrame()
        self.header.setObjectName("CardHeaderAccent" if accent else "CardHeader")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(12, 7, 10, 7)
        hl.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.meta = QLabel(meta)
        self.meta.setObjectName("CardMeta")
        hl.addWidget(self.title)
        hl.addStretch(1)
        self.header_tools = QHBoxLayout()
        self.header_tools.setSpacing(2)
        hl.addLayout(self.header_tools)
        hl.addWidget(self.meta)
        lay.addWidget(self.header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 8, 8, 8)
        self.body_layout.setSpacing(6)
        lay.addWidget(self.body, 1)

    def add_tool(self, w):
        self.header_tools.addWidget(w)


def hline():
    f = QFrame()
    f.setObjectName("HLine")
    return f


def tool_button(name: str, tip: str, color: str = theme.TEXT, checkable=False, size=18) -> QToolButton:
    b = QToolButton()
    b.setIcon(icon(name, color))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


# ---------------------------------------------------------------- image view
class _BoxItem(QGraphicsItem):
    def __init__(self, det, text: str, color: QColor, selected: bool, scale_ref: float):
        super().__init__()
        self.det, self.text, self.color, self.selected = det, text, color, selected
        x1, y1, x2, y2 = det.box
        self.rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        self.s = scale_ref
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(text)

    def boundingRect(self):
        m = 40 * self.s
        return self.rect.adjusted(-m, -m, m * 6, m)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect)
        return path

    def paint(self, p, _opt, _w=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_detection(p, self.rect, self.color, self.text, max(2.0, 3 * self.s),
                        max(12.0, 17 * self.s), self.selected)


class ImageView(QGraphicsView):
    """Zoom (wheel) / pan (drag) image view with clickable detection boxes."""
    viewChanged = Signal()
    detectionClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pix = None
        self._boxes = []
        self._placeholder = ""
        self._placeholder_error = False
        self._fit = True
        self._sync_guard = False
        self.horizontalScrollBar().valueChanged.connect(lambda *_: self._emit_change())
        self.verticalScrollBar().valueChanged.connect(lambda *_: self._emit_change())

    def _emit_change(self):
        if not self._sync_guard:
            self.viewChanged.emit()

    def set_placeholder(self, text: str, error: bool = False):
        self.scene().clear()
        self._pix = None
        self._boxes = []
        self._placeholder = text
        self._placeholder_error = error
        self.viewport().update()

    def set_image(self, img_bgr: np.ndarray, keep_view: bool = False):
        t = self.transform()
        h, v = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        self.scene().clear()
        self._boxes = []
        self._placeholder = ""
        self._pix = QGraphicsPixmapItem(bgr_to_pixmap(img_bgr))
        self._pix.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self._pix)
        self.scene().setSceneRect(QRectF(0, 0, img_bgr.shape[1], img_bgr.shape[0]))
        if keep_view and not self._fit:
            self._sync_guard = True
            self.setTransform(t)
            self.horizontalScrollBar().setValue(h)
            self.verticalScrollBar().setValue(v)
            self._sync_guard = False
        else:
            self.fit()

    def set_boxes(self, detections, label_fn, selected_id=None):
        for b in self._boxes:
            self.scene().removeItem(b)
        self._boxes = []
        if self._pix is None:
            return
        s = max(self.scene().sceneRect().width(), self.scene().sceneRect().height()) / 1000.0
        for d in detections:
            item = _BoxItem(d, label_fn(d), QColor(*class_color_rgb(d.class_id)), d.det_id == selected_id, s)
            item.setZValue(2 if d.det_id == selected_id else 1)
            self.scene().addItem(item)
            self._boxes.append(item)

    def has_image(self) -> bool:
        return self._pix is not None

    def fit(self):
        if self._pix is None:
            return
        self._fit = True
        self._sync_guard = True
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._sync_guard = False
        self.viewChanged.emit()

    def zoom(self, factor: float):
        if self._pix is None:
            return
        self._fit = False
        self.scale(factor, factor)

    def wheelEvent(self, e):
        if self._pix is None:
            return
        self.zoom(1.2 if e.angleDelta().y() > 0 else 1 / 1.2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fit:
            self.fit()

    def mouseDoubleClickEvent(self, e):
        self.fit()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(e.position().toPoint())
            if isinstance(item, _BoxItem):
                self.detectionClicked.emit(item.det.det_id)
        super().mousePressEvent(e)

    def copy_view_from(self, other: "ImageView"):
        if self._pix is None or other._pix is None:
            return
        self._sync_guard = True
        self._fit = other._fit
        self.setTransform(other.transform())
        self.horizontalScrollBar().setValue(other.horizontalScrollBar().value())
        self.verticalScrollBar().setValue(other.verticalScrollBar().value())
        self._sync_guard = False

    def drawForeground(self, p: QPainter, rect):
        if self._placeholder and self._pix is None:
            p.save()
            p.resetTransform()
            vr = QRectF(self.viewport().rect())
            p.setPen(QPen(QColor(theme.DANGER if self._placeholder_error else "#7A8299")))
            f = QFont(self.font())
            f.setPointSizeF(10)
            p.setFont(f)
            p.drawText(vr.adjusted(24, 24, -24, -24),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._placeholder)
            p.restore()


class ZoomBar(QWidget):
    def __init__(self, view: ImageView, dark=False):
        super().__init__()
        c = "#ffffff" if dark else theme.TEXT
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for name, tip, fn in (("zoom-out", "ซูมออก", lambda: view.zoom(1 / 1.25)),
                              ("zoom-in", "ซูมเข้า", lambda: view.zoom(1.25)),
                              ("fit", "พอดีกรอบ (ดับเบิลคลิกที่ภาพได้)", view.fit)):
            b = tool_button(name, tip, c, size=16)
            b.clicked.connect(fn)
            lay.addWidget(b)


# ---------------------------------------------------------------- live panel
class LiveView(QWidget):
    """Lightweight painter-based view for the live stream (frame + its own boxes)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img = None
        self._dets = []
        self._label_fn = None
        self._msg = "ยังไม่ได้เริ่มแหล่งภาพ"
        self.setMinimumSize(220, 124)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_frame(self, img_bgr, dets=(), label_fn=None):
        self._img = bgr_to_qimage(img_bgr)
        self._dets = list(dets)
        self._label_fn = label_fn
        self._msg = ""
        self.update()

    def set_message(self, msg: str):
        self._img = None
        self._msg = msg
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.fillRect(r, QColor("#0F1730"))
        if self._img is None:
            p.setPen(QColor("#A9B4D6"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._msg)
            return
        iw, ih = self._img.width(), self._img.height()
        sc = min(r.width() / iw, r.height() / ih)
        tw, th = iw * sc, ih * sc
        target = QRectF((r.width() - tw) / 2, (r.height() - th) / 2, tw, th)
        p.drawImage(target, self._img)
        if self._dets and self._label_fn:
            p.translate(target.topLeft())
            p.scale(sc, sc)
            s = 1.0 / sc
            for d in self._dets:
                x1, y1, x2, y2 = d.box
                paint_detection(p, QRectF(x1, y1, x2 - x1, y2 - y1),
                                QColor(*class_color_rgb(d.class_id)), self._label_fn(d), 2 * s, 11 * s)


# ---------------------------------------------------------------- snapshot strip
class SnapshotStrip(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SnapshotStrip")
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setIconSize(QSize(112, 70))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(2)
        self.setFixedHeight(122)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def add_snapshot(self, snap):
        h, w = snap.image.shape[:2]
        th = 140
        tw = int(w * th / h)
        thumb = cv2.resize(snap.image, (max(1, tw), th), interpolation=cv2.INTER_AREA)
        ts = _dt.datetime.fromtimestamp(snap.result.timestamp).strftime("%H:%M:%S")
        it = QListWidgetItem(QPixmap(bgr_to_pixmap(thumb)), f"{snap.index:02d}   {ts}")
        it.setData(Qt.ItemDataRole.UserRole, snap.index)
        it.setToolTip(f"ภาพที่ {snap.index:02d} • {snap.source_label}\nโมเดล {snap.result.model.name}"
                      f" ({snap.result.model.short_hash})\nวัตถุ {len(snap.result.detections)} รายการ")
        it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        it.setSizeHint(QSize(124, 104))
        self.addItem(it)
        return it

    def remove_index(self, index: int):
        for i in range(self.count()):
            if self.item(i).data(Qt.ItemDataRole.UserRole) == index:
                self.takeItem(i)
                return

    def select_index(self, index: int):
        for i in range(self.count()):
            if self.item(i).data(Qt.ItemDataRole.UserRole) == index:
                self.setCurrentRow(i)
                self.scrollToItem(self.item(i))
                return

    def current_index(self):
        it = self.currentItem()
        return None if it is None else it.data(Qt.ItemDataRole.UserRole)

    def scroll_by(self, px: int):
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() + px)


# ---------------------------------------------------------------- slider row
class SliderRow(QWidget):
    valueChanged = Signal(float)

    def __init__(self, lo: float, hi: float, step: float, value: float, decimals=2,
                 left_hint="", right_hint=""):
        super().__init__()
        self._scale = 1 / step
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        if left_hint or right_hint:
            hints = QHBoxLayout()
            a, b = QLabel(left_hint), QLabel(right_hint)
            a.setObjectName("Hint"); b.setObjectName("Hint")
            hints.addWidget(a); hints.addStretch(1); hints.addWidget(b)
            hints.addSpacing(74)
            lay.addLayout(hints)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(round(lo * self._scale)), int(round(hi * self._scale)))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setFixedWidth(58)
        self.spin.setObjectName("SliderSpin")
        self.spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.slider, 1)
        row.addWidget(self.spin)
        lay.addLayout(row)
        self.slider.valueChanged.connect(lambda v: self._from_slider(v))
        self.spin.valueChanged.connect(lambda v: self._from_spin(v))
        self.set_value(value)

    def _from_slider(self, v):
        val = v / self._scale
        if abs(self.spin.value() - val) > 1e-9:
            self.spin.blockSignals(True)
            self.spin.setValue(val)
            self.spin.blockSignals(False)
        self.valueChanged.emit(val)

    def _from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v * self._scale)))
        self.slider.blockSignals(False)
        self.valueChanged.emit(v)

    def set_value(self, v):
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round(v * self._scale)))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)

    def value(self) -> float:
        return self.spin.value()


# ---------------------------------------------------------------- detection table
class DetectionTable(QTableWidget):
    detectionSelected = Signal(int)
    HEADERS = ["#", "รหัสคลาส", "ชื่อคลาส", "ความมั่นใจ", "เลือก"]

    def __init__(self):
        super().__init__(0, len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(True)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setDefaultSectionSize(30)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._radio)
        self.itemSelectionChanged.connect(self._row_sel)
        self._ids = []
        self._guard = False

    def set_detections(self, dets, label_fn, selected_id=None):
        self._guard = True
        for b in self._group.buttons():
            self._group.removeButton(b)
        self.clearContents()
        self.setRowCount(len(dets))
        self._ids = [d.det_id for d in dets]
        for r, d in enumerate(dets):
            vals = [str(r + 1), str(d.class_id), label_fn(d.class_id), format_confidence(d.confidence)]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 2:
                    it.setForeground(QBrush(QColor(*class_color_rgb(d.class_id)).darker(130)))
                self.setItem(r, c, it)
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            rb = QRadioButton()
            hl.addStretch(1); hl.addWidget(rb); hl.addStretch(1)
            self._group.addButton(rb, d.det_id)
            self.setCellWidget(r, 4, w)
        self._guard = False
        if selected_id is not None:
            self.select_det(selected_id)

    def select_det(self, det_id):
        if det_id not in self._ids:
            return
        self._guard = True
        r = self._ids.index(det_id)
        self.selectRow(r)
        b = self._group.button(det_id)
        if b:
            b.setChecked(True)
        self._guard = False

    def _radio(self, det_id):
        if not self._guard:
            self.select_det(det_id)
            self.detectionSelected.emit(det_id)

    def _row_sel(self):
        if self._guard:
            return
        rows = self.selectionModel().selectedRows()
        if rows:
            det_id = self._ids[rows[0].row()]
            b = self._group.button(det_id)
            if b:
                self._guard = True
                b.setChecked(True)
                self._guard = False
            self.detectionSelected.emit(det_id)


class DetailPanel(QWidget):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(16)
        self.thumb = QLabel()
        self.thumb.setFixedSize(150, 112)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet(f"background:#F2F3F7;border:1px solid {theme.BORDER};border-radius:6px;")
        lay.addWidget(self.thumb)
        from PySide6.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(5)
        self.vals = {}
        for key in ("ประเภท", "รหัสคลาส", "ความมั่นใจ", "กรอบ (x, y, w, h)", "ขนาดภาพ", "โมเดล"):
            v = QLabel("-")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if key in ("ประเภท", "ความมั่นใจ"):
                v.setStyleSheet("font-weight:600;")
            self.vals[key] = v
            k = QLabel(key + ":")
            k.setObjectName("Hint")
            form.addRow(k, v)
        lay.addLayout(form, 1)

    def clear(self, msg="เลือกวัตถุจากตารางหรือคลิกกรอบบนภาพ"):
        self.thumb.setPixmap(QPixmap())
        self.thumb.setText("")
        for v in self.vals.values():
            v.setText("-")
        self.vals["ประเภท"].setText(msg)

    def show_detection(self, snap, det):
        x, y, w, h = det.xywh_int()
        H, W = snap.image.shape[:2]
        pad = int(0.08 * max(w, h))
        crop = snap.image[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)]
        if crop.size:
            pm = bgr_to_pixmap(crop).scaled(self.thumb.size() - QSize(6, 6),
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self.thumb.setPixmap(pm)
        orig = snap.class_names.get(int(det.class_id), f"class_{det.class_id}")
        lab = snap.label(det.class_id)
        self.vals["ประเภท"].setText(lab if lab == orig else f"{lab}  (ต้นฉบับ: {orig})")
        self.vals["รหัสคลาส"].setText(str(det.class_id))
        self.vals["ความมั่นใจ"].setText(format_confidence(det.confidence))
        self.vals["กรอบ (x, y, w, h)"].setText(f"{x}, {y}, {w}, {h}")
        self.vals["ขนาดภาพ"].setText(f"{W} × {H}")
        self.vals["โมเดล"].setText(f"{snap.result.model.name} ({snap.result.model.short_hash})")
