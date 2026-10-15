"""แสดงข้อมูลโมเดลหลังเปิด: ชนิดไฟล์ adapter task input คลาส device สถานะ และข้อจำกัด"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QAbstractItemView)

from ...adapters.base import ModelInfo


class ModelInfoDialog(QDialog):
    def __init__(self, info: ModelInfo, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"ข้อมูลโมเดล — {info.identity.name}")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        rows = info.summary_rows()
        t = QTableWidget(len(rows), 2)
        t.setHorizontalHeaderLabels(["รายการ", "ค่า"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setWordWrap(True)
        for r, (k, v) in enumerate(rows):
            t.setItem(r, 0, QTableWidgetItem(k))
            t.setItem(r, 1, QTableWidgetItem(v))
        t.resizeRowsToContents()
        tabs.addTab(t, "สรุป")

        reg = info.classes
        c = QTableWidget(reg.count, 2)
        c.setHorizontalHeaderLabels(["class_id", "ชื่อคลาส"])
        c.verticalHeader().setVisible(False)
        c.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        c.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for r, (k, v) in enumerate(sorted(reg.names.items())):
            c.setItem(r, 0, QTableWidgetItem(str(k)))
            c.setItem(r, 1, QTableWidgetItem(v))
        tabs.addTab(c, f"คลาส ({reg.count})")

        notes = list(info.caps.limitations) + list(reg.notes)
        if not info.caps.grad_cam:
            notes.append(info.caps.grad_cam_reason)
        notes.append("ไฟล์ .pt โหลดผ่าน pickle — เปิดเฉพาะไฟล์จากแหล่งที่เชื่อถือได้"
                     if info.identity.file_format == ".pt" else
                     "ONNX: รองรับเฉพาะ output layout ที่รู้จัก ไม่เดารูปแบบ output")
        notes.append("ค่าความมั่นใจคือ score ของโมเดล ไม่ใช่ accuracy/mAP — โปรแกรมไม่แสดงค่าความแม่นยำ "
                     "เพราะไม่มีชุดข้อมูล ground-truth")
        lab = QLabel("• " + "\n• ".join(n for n in notes if n))
        lab.setWordWrap(True)
        lab.setContentsMargins(12, 12, 12, 12)
        lab.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        tabs.addTab(lab, "ข้อจำกัดสำคัญ")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.button(QDialogButtonBox.StandardButton.Close).setText("ปิด")
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
