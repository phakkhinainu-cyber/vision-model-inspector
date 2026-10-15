"""Small vector icons painted with QPainter (no third-party icon files)."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _pen(c, w=1.8):
    p = QPen(QColor(c), w)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _draw(name: str, p: QPainter, c: str):
    s = 24.0
    p.setPen(_pen(c))
    p.setBrush(Qt.BrushStyle.NoBrush)
    fill = QColor(c)
    if name == "folder":
        path = QPainterPath()
        path.moveTo(3, 7); path.lineTo(3, 19); path.lineTo(21, 19); path.lineTo(21, 9)
        path.lineTo(11, 9); path.lineTo(9, 6); path.lineTo(4, 6); path.closeSubpath()
        p.setBrush(fill); p.drawPath(path)
    elif name == "play":
        p.setBrush(fill)
        p.drawPolygon(QPolygonF([QPointF(7, 4.5), QPointF(19.5, 12), QPointF(7, 19.5)]))
    elif name == "stop":
        p.setBrush(fill); p.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    elif name == "pause":
        p.setBrush(fill); p.drawRect(QRectF(6.5, 5, 4, 14)); p.drawRect(QRectF(13.5, 5, 4, 14))
    elif name == "camera":
        p.setBrush(fill)
        path = QPainterPath()
        path.addRoundedRect(QRectF(2.5, 7, 19, 13), 2.5, 2.5)
        path.addRect(QRectF(8, 4.5, 8, 3.5))
        p.drawPath(path)
        p.setBrush(QColor("white") if c != "#ffffff" else QColor("#5B3FD9"))
        p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(12, 13.5), 3.8, 3.8)
    elif name == "chart":
        p.setBrush(fill); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(4, 12, 4, 8)); p.drawRect(QRectF(10, 5, 4, 15)); p.drawRect(QRectF(16, 9, 4, 11))
    elif name == "export":
        p.drawLine(QPointF(12, 15), QPointF(12, 3)); p.drawLine(QPointF(7.5, 7.5), QPointF(12, 3))
        p.drawLine(QPointF(16.5, 7.5), QPointF(12, 3))
        path = QPainterPath(); path.moveTo(5, 11); path.lineTo(5, 20); path.lineTo(19, 20); path.lineTo(19, 11)
        p.drawPath(path)
    elif name == "refresh":
        p.drawArc(QRectF(5, 5, 14, 14), 30 * 16, 290 * 16)
        p.setBrush(fill); p.drawPolygon(QPolygonF([QPointF(19.5, 3.5), QPointF(20, 10), QPointF(14, 8.5)]))
    elif name == "eye":
        path = QPainterPath(); path.moveTo(2, 12); path.quadTo(12, 1, 22, 12); path.quadTo(12, 23, 2, 12)
        p.drawPath(path); p.setBrush(fill); p.drawEllipse(QPointF(12, 12), 3.5, 3.5)
    elif name == "expand":
        for a, b, c1, d in ((4, 9, 4, 4), (9, 4, 4, 4), (15, 4, 20, 4), (20, 9, 20, 4),
                            (4, 15, 4, 20), (9, 20, 4, 20), (20, 15, 20, 20), (15, 20, 20, 20)):
            p.drawLine(QPointF(a, b), QPointF(c1, d))
    elif name == "info":
        p.setBrush(fill); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QRectF(2, 2, 20, 20))
        p.setPen(_pen("#ffffff", 2.2)); p.drawLine(QPointF(12, 11), QPointF(12, 17)); p.drawPoint(QPointF(12, 7.3))
    elif name == "search":
        p.drawEllipse(QRectF(4, 4, 11, 11)); p.drawLine(QPointF(13.5, 13.5), QPointF(20, 20))
    elif name == "settings":
        p.drawEllipse(QPointF(12, 12), 3, 3)
        for i in range(8):
            import math
            a = i * math.pi / 4
            p.drawLine(QPointF(12 + 6 * math.cos(a), 12 + 6 * math.sin(a)),
                       QPointF(12 + 8.5 * math.cos(a), 12 + 8.5 * math.sin(a)))
        p.drawEllipse(QPointF(12, 12), 6, 6)
    elif name == "trash":
        p.drawLine(QPointF(4, 6.5), QPointF(20, 6.5)); p.drawRect(QRectF(9, 3.5, 6, 3))
        path = QPainterPath(); path.moveTo(6, 6.5); path.lineTo(7, 20.5); path.lineTo(17, 20.5); path.lineTo(18, 6.5)
        p.drawPath(path)
    elif name in ("left", "right"):
        if name == "left":
            p.drawPolyline(QPolygonF([QPointF(15, 5), QPointF(8, 12), QPointF(15, 19)]))
        else:
            p.drawPolyline(QPolygonF([QPointF(9, 5), QPointF(16, 12), QPointF(9, 19)]))
    elif name == "fit":
        p.drawRect(QRectF(4, 6, 16, 12)); p.drawLine(QPointF(8, 12), QPointF(16, 12))
    elif name == "zoom-in":
        p.drawEllipse(QRectF(3, 3, 13, 13)); p.drawLine(QPointF(14, 14), QPointF(21, 21))
        p.drawLine(QPointF(6.5, 9.5), QPointF(12.5, 9.5)); p.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 12.5))
    elif name == "zoom-out":
        p.drawEllipse(QRectF(3, 3, 13, 13)); p.drawLine(QPointF(14, 14), QPointF(21, 21))
        p.drawLine(QPointF(6.5, 9.5), QPointF(12.5, 9.5))
    elif name == "link":
        p.drawRoundedRect(QRectF(2.5, 8.5, 10, 7), 3.5, 3.5); p.drawRoundedRect(QRectF(11.5, 8.5, 10, 7), 3.5, 3.5)
    elif name == "tag":
        path = QPainterPath(); path.moveTo(3, 4); path.lineTo(12, 4); path.lineTo(21, 13); path.lineTo(13, 21)
        path.lineTo(3, 12); path.closeSubpath(); p.drawPath(path); p.setBrush(fill); p.drawEllipse(QPointF(8, 9), 1.6, 1.6)
    elif name == "cube":
        path = QPainterPath(); path.moveTo(12, 3); path.lineTo(20, 7.5); path.lineTo(20, 16.5); path.lineTo(12, 21)
        path.lineTo(4, 16.5); path.lineTo(4, 7.5); path.closeSubpath(); p.drawPath(path)
        p.drawLine(QPointF(4, 7.5), QPointF(12, 12)); p.drawLine(QPointF(20, 7.5), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(12, 21))
    elif name == "image":
        p.drawRoundedRect(QRectF(3, 5, 18, 14), 2, 2); p.setBrush(fill)
        p.drawPolygon(QPolygonF([QPointF(5, 17), QPointF(10, 11), QPointF(13, 14), QPointF(15, 12), QPointF(19, 17)]))
    else:
        p.drawEllipse(QRectF(4, 4, 16, 16))
    _ = s


@lru_cache(maxsize=256)
def icon(name: str, color: str = "#1E2433", size: int = 24) -> QIcon:
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.setDevicePixelRatio(scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(size / 24.0, size / 24.0)
        _draw(name, p, color)
        p.end()
        ic.addPixmap(pm)
    return ic


def pixmap(name: str, color: str, size: int) -> QPixmap:
    return icon(name, color, size).pixmap(size, size)
