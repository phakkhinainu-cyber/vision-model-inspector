"""เลือกโฟลเดอร์และรายการที่จะส่งออก"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)

from ...core.export import ExportOptions


class ExportDialog(QDialog):
    def __init__(self, folder: str, has_gradcam: bool, has_filter: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ส่งออกผลการวิเคราะห์")
        self.resize(560, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("โฟลเดอร์ปลายทาง (สร้างโฟลเดอร์ย่อยใหม่ทุกครั้ง ไม่เขียนทับไฟล์เดิม):"))
        row = QHBoxLayout()
        self.path = QLineEdit(folder or os.path.expanduser("~"))
        b = QPushButton("เลือก…")
        b.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(b)
        lay.addLayout(row)
        grid = QGridLayout()
        self.cb = {}
        items = [("original", "ภาพต้นฉบับ (สำเนา PNG)", True, True),
                 ("annotated", "ภาพพร้อมกรอบตรวจจับ", True, True),
                 ("heatmap", "ภาพ Heatmap", has_gradcam, has_gradcam),
                 ("overlay", "ภาพซ้อน Heatmap", has_gradcam, has_gradcam),
                 ("comparison", "ภาพเปรียบเทียบสองฝั่ง", True, True),
                 ("csv", "ตาราง detections (CSV)", True, True),
                 ("json", "metadata (JSON) — model hash, คลาส, ค่าตั้ง, device, เวอร์ชัน", True, True)]
        for i, (k, text, enabled, checked) in enumerate(items):
            c = QCheckBox(text)
            c.setEnabled(enabled)
            c.setChecked(checked)
            if not enabled:
                c.setToolTip("ยังไม่มีผล Grad-CAM สำหรับภาพนี้")
            self.cb[k] = c
            grid.addWidget(c, i // 2, i % 2)
        lay.addLayout(grid)
        self.only_visible = QCheckBox("ใช้ตัวกรองคลาสกับภาพกรอบและ CSV (ไม่รวมคลาสที่ซ่อน)")
        self.only_visible.setEnabled(has_filter)
        lay.addWidget(self.only_visible)
        note = QLabel("ไฟล์ทั้งหมดบันทึกในเครื่องนี้เท่านั้น โปรแกรมไม่ส่งภาพหรือโมเดลออกไปภายนอก")
        note.setObjectName("Hint")
        lay.addWidget(note)
        lay.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("ส่งออก")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("ยกเลิก")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ปลายทาง", self.path.text())
        if d:
            self.path.setText(d)

    def options(self, opacity: float) -> ExportOptions:
        o = ExportOptions(heatmap_opacity=opacity, only_visible=self.only_visible.isChecked())
        for k, c in self.cb.items():
            setattr(o, k, c.isChecked() and c.isEnabled())
        return o
