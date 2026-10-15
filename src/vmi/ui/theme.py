"""Colours, fonts and the Qt style sheet (UI แบบ C: ขาว เทาอ่อน น้ำเงินเข้ม ม่วง)."""
from __future__ import annotations

import logging
import os

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from ..config import resource_path

log = logging.getLogger(__name__)

NAVY = "#1F2B4D"
NAVY_2 = "#2A3A63"
PURPLE = "#5B3FD9"
PURPLE_2 = "#7350EC"
PURPLE_SOFT = "#ECE8FD"
GREEN = "#23964A"
GREEN_2 = "#2DAE58"
BG = "#EEF1F6"
CARD = "#FFFFFF"
BORDER = "#D8DDE8"
TEXT = "#1E2433"
MUTED = "#5F6880"
INFO_BG = "#E7F0FD"
INFO_FG = "#1E4E9C"
DANGER = "#C93636"
WARN_BG = "#FFF4DD"

FONT_FAMILY = "IBM Plex Sans Thai"
FALLBACK_FAMILIES = ["Leelawadee UI", "Tahoma", "Noto Sans Thai", "Loma", "Sans Serif"]


def load_fonts() -> str:
    """Load the bundled OFL Thai font. Returns the family actually used."""
    folder = resource_path("fonts")
    loaded = set()
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.lower().endswith((".ttf", ".otf")):
                fid = QFontDatabase.addApplicationFont(os.path.join(folder, name))
                if fid >= 0:
                    loaded.update(QFontDatabase.applicationFontFamilies(fid))
    if FONT_FAMILY in loaded:
        return FONT_FAMILY
    families = set(QFontDatabase.families())
    for fam in FALLBACK_FAMILIES:
        if fam in families:
            log.warning("bundled Thai font not found, using %s", fam)
            return fam
    return QApplication.font().family()


def app_font(family: str, pt: float = 9.5) -> QFont:
    f = QFont(family)
    f.setPointSizeF(pt)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def stylesheet(family: str) -> str:
    return f"""
* {{ font-family: "{family}"; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#Root {{ background: {BG}; }}
QToolTip {{ background: {NAVY}; color: white; border: none; padding: 5px 8px; }}

/* ---------- header bar ---------- */
QFrame#HeaderBar {{ background: {NAVY}; }}
QFrame#HeaderBar QLabel {{ color: white; }}
QLabel#AppTitle {{ font-size: 15pt; font-weight: 600; color: white; }}
QLabel#AppSubtitle {{ font-size: 12pt; color: white; }}
QLabel#HeaderMeta {{ color: #C9D2EA; font-size: 9pt; }}
QFrame#HeaderSep {{ background: #4A5A85; max-width: 1px; min-width: 1px; }}
QLabel#Logo {{ background: {PURPLE}; border-radius: 6px; }}

/* ---------- toolbar ---------- */
QFrame#ToolBar {{ background: {BG}; }}
QPushButton {{
    background: white; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 14px; min-height: 22px; font-weight: 500;
}}
QPushButton:hover {{ border-color: {PURPLE_2}; background: #FAF9FF; }}
QPushButton:pressed {{ background: {PURPLE_SOFT}; }}
QPushButton:disabled {{ color: #A0A7B8; background: #F3F4F8; border-color: #E2E5EE; }}
QPushButton[kind="primary"] {{ background: {PURPLE}; border: 1px solid {PURPLE}; color: white; }}
QPushButton[kind="primary"]:hover {{ background: {PURPLE_2}; }}
QPushButton[kind="primary"]:disabled {{ background: #B9AEEB; border-color: #B9AEEB; color: #F2F0FB; }}
QPushButton[kind="success"] {{ background: {GREEN}; border: 1px solid {GREEN}; color: white; }}
QPushButton[kind="success"]:hover {{ background: {GREEN_2}; }}
QPushButton[kind="success"]:disabled {{ background: #9FD0AF; border-color: #9FD0AF; color: #F1FAF3; }}
QPushButton[kind="flat"] {{ background: transparent; border: none; padding: 4px; }}
QPushButton[kind="flat"]:hover {{ background: rgba(91,63,217,0.10); }}
QPushButton[kind="mini"] {{ padding: 2px 6px; min-height: 18px; }}
QToolButton {{ border: none; border-radius: 4px; padding: 3px; background: transparent; }}
QToolButton:hover {{ background: rgba(91,63,217,0.12); }}
QToolButton:checked {{ background: {PURPLE_SOFT}; }}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: white; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px;
    min-height: 20px; selection-background-color: {PURPLE};
}}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {PURPLE}; }}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background: #F3F4F8; color: #9AA1B2; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {BORDER};
    selection-background-color: {PURPLE_SOFT}; selection-color: {TEXT}; outline: none; }}

/* ---------- cards ---------- */
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#CardAccent {{ background: {CARD}; border: 1px solid #B9AAF2; border-radius: 8px; }}
QFrame#CardHeader {{ background: #F6F7FB; border-top-left-radius: 8px; border-top-right-radius: 8px;
    border-bottom: 1px solid {BORDER}; }}
QFrame#CardHeaderAccent {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {PURPLE}, stop:1 {PURPLE_2});
    border-top-left-radius: 7px; border-top-right-radius: 7px; }}
QFrame#CardHeaderAccent QLabel {{ color: white; }}
QLabel#CardTitle {{ font-weight: 600; font-size: 10.5pt; }}
QFrame#CardHeaderAccent QLabel#CardTitle {{ font-size: 11.5pt; }}
QLabel#CardMeta {{ color: {MUTED}; font-size: 8.5pt; }}
QFrame#CardHeaderAccent QLabel#CardMeta {{ color: #EDE8FF; }}

QFrame#LiveCard {{ background: {NAVY}; border-radius: 8px; border: 1px solid {NAVY}; }}
QFrame#LiveCard QLabel {{ color: white; }}
QLabel#LiveTitle {{ font-weight: 600; }}
QLabel#Badge {{ background: rgba(255,186,73,0.95); color: #3A2600; border-radius: 4px;
    padding: 2px 6px; font-size: 8.5pt; font-weight: 600; }}

QFrame#InfoBanner {{ background: {INFO_BG}; border: 1px solid #C8DAF7; border-radius: 8px; }}
QFrame#InfoBanner QLabel {{ color: {INFO_FG}; }}
QFrame#WarnBanner {{ background: {WARN_BG}; border: 1px solid #F1D7A0; border-radius: 6px; }}

/* ---------- settings panel ---------- */
QLabel#FieldLabel {{ font-weight: 500; }}
QLabel#Hint {{ color: {MUTED}; font-size: 8.5pt; }}
QLabel#SectionTitle {{ font-weight: 600; color: {PURPLE}; margin-top: 4px; }}
QSlider::groove:horizontal {{ height: 4px; background: #DCDFEA; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {PURPLE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {PURPLE}; border: 3px solid white; width: 14px; height: 14px;
    margin: -7px 0; border-radius: 10px; }}
QSlider::handle:horizontal:disabled {{ background: #B9AEEB; }}
QFrame#HLine {{ background: {BORDER}; max-height: 1px; min-height: 1px; }}

/* ---------- tables / lists ---------- */
QTableWidget, QTableView {{ background: white; border: none; gridline-color: #E6E9F0;
    selection-background-color: {PURPLE_SOFT}; selection-color: {TEXT}; alternate-background-color: #FAFBFD; }}
QHeaderView::section {{ background: white; border: none; border-bottom: 1px solid {BORDER};
    border-right: 1px solid #EEF0F5; padding: 5px; font-weight: 600; }}
QListWidget#SnapshotStrip {{ background: transparent; border: none; outline: none; }}
QListWidget#SnapshotStrip::item {{ border: 2px solid transparent; border-radius: 6px; padding: 3px;
    margin: 2px; color: {TEXT}; }}
QListWidget#SnapshotStrip::item:selected {{ border: 2px solid {PURPLE}; background: {PURPLE_SOFT};
    color: {PURPLE}; }}
QListWidget#SnapshotStrip::item:hover {{ background: #F4F2FE; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; background: white; top: -1px; }}
QTabBar::tab {{ background: #E4E7F0; border: 1px solid {BORDER}; padding: 6px 14px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: white; color: {PURPLE}; font-weight: 600; }}

QStatusBar {{ background: white; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 8px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: #D5CFF6; }}
QScrollArea {{ border: none; background: transparent; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {PURPLE}; }}
QGraphicsView {{ border: none; background: #F2F3F7; }}
QProgressBar {{ border: 1px solid {BORDER}; border-radius: 4px; background: white; text-align: center; }}
QProgressBar::chunk {{ background: {PURPLE}; border-radius: 3px; }}
"""
