"""หน้าจัดการคลาส: ชื่อต้นฉบับ ชื่อแสดงผล ตัวกรองการแสดงผล และการนำเข้า mapping."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ...core.classes import (ClassMappingError, ClassRegistry, SOURCE_FILE, SOURCE_LABELS_TH,
                             compare_mapping, load_mapping_file)
from ..icons import icon

ORDER_HELP = ("รูปแบบไฟล์ที่นำเข้าได้:\n"
              "• data.yaml — ใช้คีย์ names (list หรือ {id: name}) และ nc ถ้ามี\n"
              "• classes.txt — 1 บรรทัด = 1 คลาส บรรทัดแรกคือรหัส 0 ห้ามมีบรรทัดว่างคั่น\n"
              "• JSON — list หรือ {\"0\": \"ชื่อ\", …}\n"
              "ลำดับชื่อต้องตรงกับลำดับตอนฝึกโมเดล มิฉะนั้นป้ายชื่อจะผิดความหมาย")


class ClassManagerDialog(QDialog):
    def __init__(self, registry: ClassRegistry, display: dict, hidden: set, expected_count,
                 model_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"จัดการคลาส — {model_name}")
        self.resize(760, 600)
        self.registry = registry
        self.expected = expected_count
        self.new_registry = None             # set when a mapping was imported & confirmed
        self.mapping_file = ""

        lay = QVBoxLayout(self)
        self.src_label = QLabel()
        self.src_label.setWordWrap(True)
        lay.addWidget(self.src_label)
        if registry.notes:
            note = QLabel("\n".join(registry.notes))
            note.setWordWrap(True)
            fr = QFrame(); fr.setObjectName("WarnBanner")
            fl = QVBoxLayout(fr); fl.setContentsMargins(10, 6, 10, 6); fl.addWidget(note)
            lay.addWidget(fr)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("ค้นหาคลาส (รหัส ชื่อต้นฉบับ หรือชื่อแสดงผล)")
        self.search.addAction(icon("search", "#5F6880"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.rb_all = QRadioButton("แสดงทุกคลาส")
        self.rb_some = QRadioButton("แสดงเฉพาะคลาสที่เลือก")
        (self.rb_some if hidden else self.rb_all).setChecked(True)
        self.rb_all.toggled.connect(self._mode)
        top.addWidget(self.rb_all)
        top.addWidget(self.rb_some)
        lay.addLayout(top)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["แสดง", "class_id", "ชื่อต้นฉบับ (จากโมเดล/ไฟล์)", "ชื่อแสดงผล (ตั้งเอง)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)

        hint = QLabel("ชื่อแสดงผลเก็บแยกจากไฟล์โมเดล (อ้างอิง SHA-256 ของโมเดล + class_id) ไม่แก้ไขไฟล์โมเดล • "
                      "ตัวกรองมีผลกับการแสดงผล/ตาราง/การส่งออกเท่านั้น ไม่ได้เปลี่ยนความสามารถของโมเดล")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        btns = QHBoxLayout()
        b_imp = QPushButton("นำเข้า mapping (data.yaml / classes.txt / JSON)…")
        b_imp.clicked.connect(self._import)
        b_imp.setToolTip(ORDER_HELP)
        b_help = QPushButton("รูปแบบไฟล์ / ลำดับคลาส")
        b_help.clicked.connect(lambda: QMessageBox.information(self, "รูปแบบไฟล์ mapping", ORDER_HELP))
        b_reset = QPushButton("ล้างชื่อแสดงผล")
        b_reset.clicked.connect(self._reset_display)
        b_allon = QPushButton("เลือกทั้งหมด")
        b_allon.clicked.connect(lambda: self._set_checks(True))
        b_alloff = QPushButton("ไม่เลือกทั้งหมด")
        b_alloff.clicked.connect(lambda: self._set_checks(False))
        for b in (b_imp, b_help, b_reset):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(b_allon)
        btns.addWidget(b_alloff)
        lay.addLayout(btns)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("บันทึก")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("ยกเลิก")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._fill(registry, display, hidden)

    # ------------------------------------------------------------------
    def _fill(self, reg: ClassRegistry, display: dict, hidden: set):
        self.src_label.setText(
            f"<b>แหล่งที่มาของรายชื่อ:</b> {SOURCE_LABELS_TH.get(reg.source, reg.source)}"
            f"{' — ' + reg.source_detail if reg.source_detail else ''} • <b>จำนวน:</b> {reg.count} คลาส"
            + ("" if reg.count_verified else " (ตรวจกับ output ของโมเดลไม่ได้)"))
        self.table.setRowCount(reg.count)
        for r, (cid, name) in enumerate(sorted(reg.names.items())):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked if cid in hidden else Qt.CheckState.Checked)
            self.table.setItem(r, 0, chk)
            it = QTableWidgetItem(str(cid))
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 1, it)
            it = QTableWidgetItem(name)
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(r, 2, it)
            self.table.setItem(r, 3, QTableWidgetItem(display.get(cid, "")))
        self._mode()

    def _mode(self):
        self.table.setColumnHidden(0, self.rb_all.isChecked())

    def _filter(self, text):
        t = text.strip().lower()
        for r in range(self.table.rowCount()):
            cells = [self.table.item(r, c).text().lower() for c in (1, 2, 3)]
            self.table.setRowHidden(r, bool(t) and not any(t in c for c in cells))

    def _set_checks(self, on: bool):
        self.rb_some.setChecked(True)
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                self.table.item(r, 0).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _reset_display(self):
        for r in range(self.table.rowCount()):
            self.table.item(r, 3).setText("")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "นำเข้ารายชื่อคลาส", "",
                                              "Class mapping (*.yaml *.yml *.txt *.json)")
        if not path:
            return
        try:
            names = load_mapping_file(path)
            diffs = compare_mapping(self.registry.names, names, self.expected)
        except ClassMappingError as e:
            QMessageBox.critical(self, "นำเข้าไม่สำเร็จ", f"{e}\n\n{ORDER_HELP}")
            return
        if not diffs:
            QMessageBox.information(self, "นำเข้า", "รายชื่อในไฟล์ตรงกับที่ใช้อยู่แล้ว")
            return
        if self.registry.names_available and not self.registry.looks_generic():
            preview = "\n".join(f"  {k}: {a!s} → {b!s}" for k, a, b in diffs[:12])
            more = f"\n  … อีก {len(diffs) - 12} รายการ" if len(diffs) > 12 else ""
            ok = QMessageBox.warning(
                self, "ชื่อคลาสขัดกับ metadata ในโมเดล",
                f"ไฟล์ที่นำเข้ามีชื่อต่างจากชื่อในโมเดล {len(diffs)} รายการ:\n{preview}{more}\n\n"
                "ต้องการใช้ชื่อจากไฟล์แทนหรือไม่? (ไฟล์โมเดลจะไม่ถูกแก้ไข)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ok != QMessageBox.StandardButton.Yes:
                return
        reg = ClassRegistry(names, SOURCE_FILE, count_verified=self.expected is not None,
                            source_detail=path)
        self.new_registry = reg
        self.mapping_file = path
        display = self.display_names()
        hidden = self.hidden_ids()
        self.registry = reg
        self._fill(reg, display, hidden)

    # ------------------------------------------------------------------
    def display_names(self) -> dict:
        out = {}
        for r in range(self.table.rowCount()):
            v = self.table.item(r, 3).text().strip()
            if v:
                out[int(self.table.item(r, 1).text())] = v
        return out

    def hidden_ids(self) -> set:
        if self.rb_all.isChecked():
            return set()
        return {int(self.table.item(r, 1).text()) for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() != Qt.CheckState.Checked}
