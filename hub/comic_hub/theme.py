"""
The pastel pink Aero (Windows Vista/7) look, as one Qt stylesheet.

Colours come from the prototype (docs/DESIGN.md section 11). Glossy surfaces
use Qt's ``qlineargradient`` with a hard stop near the middle, which is what
gives Aero buttons and toolbars their split shine.
"""

from __future__ import annotations

import os

# Qt stylesheets load images from files, so the arrow icons live in assets/.
ASSETS = os.path.join(os.path.dirname(__file__), "assets").replace(os.sep, "/")

# ---------- tokens ----------
DESKTOP = "#f6c7d6"
PANE = "#ffffff"
PANE_ALT = "#fff5f8"
TEXT = "#4a3340"
MUTED = "#8e7381"
ACCENT = "#d9568a"
ACCENT_TEXT = "#b83c70"
BORDER = "#d9a7ba"
BORDER_SOFT = "#efd3dd"
BORDER_STRONG = "#c98aa3"
SELECT_BORDER = "#edb3c8"
CANVAS = "#d8d8dc"   # neutral on purpose: pink around a page skews colour judgement
TAIL = "#2f7fd1"
DANGER = "#c8323a"
DANGER_SOFT = "#ffe5e6"
OK = "#237550"
OK_SOFT = "#e1f5ea"

STATUS_LABELS = {"thumbs": "Thumbs", "pencils": "Pencils", "inks": "Inks",
                 "colors": "Colors", "letters": "Letters", "done": "Done"}


def _v(*stops: tuple[float, str]) -> str:
    """A vertical gradient, top to bottom."""
    return "qlineargradient(x1:0, y1:0, x2:0, y2:1, " + ", ".join(f"stop:{p} {c}" for p, c in stops) + ")"


GLASS = _v((0, "rgba(255,255,255,235)"), (0.06, "rgba(251,225,234,220)"), (0.5, "rgba(247,204,219,210)"), (1, "rgba(244,192,210,230)"))
TOOLBAR = _v((0, "#ffffff"), (0.5, "#fcebf1"), (0.51, "#f8dde7"), (1, "#f6d3e0"))
BUTTON = _v((0, "#ffffff"), (0.48, "#fceef3"), (0.5, "#f8dce7"), (1, "#f4ccdb"))
BUTTON_HOVER = _v((0, "#fff8fb"), (0.48, "#fde2ec"), (0.5, "#f9cddf"), (1, "#f6bdd2"))
BUTTON_DOWN = _v((0, "#f6c4d6"), (0.5, "#f8d3e1"), (0.51, "#f4c3d5"), (1, "#f8d6e3"))
DEFAULT = _v((0, "#ffeff5"), (0.48, "#fcd3e2"), (0.5, "#f6b3cc"), (1, "#f9c6d9"))
SELECT = _v((0, "#fff6f9"), (1, "#fbdce7"))
PROGRESS = _v((0, "#bff0c8"), (0.5, "#6fd27f"), (0.51, "#4cbf5e"), (1, "#8fe09b"))

STYLESHEET = f"""
* {{ color: {TEXT}; font-family: "Segoe UI", "Open Sans", "DejaVu Sans", sans-serif; font-size: 9pt; }}
QMainWindow {{ background: {GLASS}; }}
QDialog {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 {PANE_ALT}); }}
QScrollArea {{ background: {PANE}; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: {PANE}; }}
QMainWindow::separator {{ width: 0; height: 0; }}
#Client {{ background: {PANE}; border: 1px solid {BORDER_STRONG}; }}

/* address row */
#RoundButton {{ border: 1px solid {BORDER_STRONG}; border-radius: 12px; background: {BUTTON};
               min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0; }}
#RoundButton:hover {{ background: {BUTTON_HOVER}; }}
#RoundButton:disabled {{ background: #f6f0f2; border-color: {BORDER_SOFT}; }}
#Crumb, #Search {{ background: rgba(255,255,255,235); border: 1px solid {BORDER}; border-top-color: {BORDER_STRONG};
                  border-radius: 2px; padding: 2px 6px; min-height: 18px; }}

/* command bar */
#CommandBar {{ background: {TOOLBAR}; border: 0; border-bottom: 1px solid {BORDER_SOFT}; padding: 2px 6px; spacing: 2px; }}
#CommandBar QToolButton {{ border: 1px solid transparent; border-radius: 3px; padding: 3px 8px; background: transparent; }}
#CommandBar QToolButton:hover {{ border-color: {SELECT_BORDER}; background: {SELECT}; }}
#CommandBar QToolButton:pressed, #CommandBar QToolButton:checked {{ border-color: {BORDER}; background: {BUTTON_DOWN}; }}
#CommandBar QToolButton[primary="true"] {{ font-weight: 600; }}

/* navigation pane */
#NavPane {{ show-decoration-selected: 0; background: {PANE_ALT}; border: 0; border-right: 1px solid {BORDER_SOFT}; padding: 8px 4px; outline: 0; }}
#NavPane::item {{ padding: 3px 4px; border: 1px solid transparent; border-radius: 3px; }}
#NavPane::item:hover {{ border-color: {BORDER_SOFT}; background: #ffffff; }}
#NavPane::branch {{ background: transparent; border: 0; }}
#NavPane::item:selected {{ border-color: {SELECT_BORDER}; background: {SELECT}; color: {TEXT}; }}

/* scroll bars: thin glossy thumbs */
QScrollBar:vertical {{ background: {PANE_ALT}; width: 12px; margin: 0; border-left: 1px solid {BORDER_SOFT}; }}
QScrollBar:horizontal {{ background: {PANE_ALT}; height: 12px; margin: 0; border-top: 1px solid {BORDER_SOFT}; }}
QScrollBar::handle:vertical {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffffff, stop:0.5 #fbe1ea, stop:0.51 #f6cfdd, stop:1 #f3c3d5);
                              border: 1px solid {BORDER_STRONG}; border-radius: 3px; min-height: 24px; margin: 1px; }}
QScrollBar::handle:horizontal {{ background: {BUTTON}; border: 1px solid {BORDER_STRONG}; border-radius: 3px; min-width: 24px; margin: 1px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* buttons */
QPushButton {{ border: 1px solid {BORDER_STRONG}; border-radius: 3px; background: {BUTTON}; padding: 3px 14px; min-width: 60px; min-height: 18px; }}
QPushButton:hover {{ background: {BUTTON_HOVER}; }}
QPushButton:pressed {{ background: {BUTTON_DOWN}; }}
QPushButton:default {{ border-color: {ACCENT}; background: {DEFAULT}; }}
QPushButton:disabled {{ color: #b9a5af; border-color: {BORDER_SOFT}; background: #faf5f7; }}

/* inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: #ffffff; border: 1px solid {BORDER}; border-top-color: {BORDER_STRONG}; border-radius: 2px;
    padding: 2px 4px; min-height: 18px; selection-background-color: {SELECT_BORDER}; selection-color: {TEXT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 15px; border-left: 1px solid {BORDER_SOFT}; background: {BUTTON}; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 2px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 2px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {BUTTON_HOVER}; }}
QAbstractSpinBox::up-arrow {{ image: url("{ASSETS}/arrow-up.svg"); width: 8px; height: 5px; }}
QAbstractSpinBox::down-arrow {{ image: url("{ASSETS}/arrow-down.svg"); width: 8px; height: 5px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 18px; border-left: 1px solid {BORDER_SOFT}; background: {BUTTON}; }}
QComboBox::down-arrow {{ image: url("{ASSETS}/arrow-down.svg"); width: 8px; height: 5px; }}
QComboBox QAbstractItemView {{ background: #ffffff; selection-background-color: {SELECT_BORDER}; selection-color: {TEXT}; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}

/* group boxes and tabs */
QGroupBox {{ border: 1px solid {BORDER_SOFT}; border-radius: 3px; margin-top: 10px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {ACCENT_TEXT}; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; top: -1px; background: #ffffff; }}
QTabBar::tab {{ border: 1px solid {BORDER}; border-bottom: 0; border-top-left-radius: 3px; border-top-right-radius: 3px;
               background: {TOOLBAR}; padding: 3px 12px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: #ffffff; padding-bottom: 4px; }}
QTabBar::tab:disabled {{ color: #b9a5af; }}

/* lists, tables, tree */
QListWidget, QTableWidget, QTreeWidget {{ background: #ffffff; border: 0; outline: 0; }}
QListWidget::item {{ border: 1px solid transparent; border-radius: 3px; padding: 2px; }}
QListWidget::item:hover {{ border-color: {BORDER_SOFT}; background: #fffafc; }}
QListWidget::item:selected {{ border-color: {SELECT_BORDER}; background: {SELECT}; color: {TEXT}; }}
QTableWidget {{ gridline-color: transparent; }}
QTableWidget::item {{ padding: 3px 8px; }}
QTableWidget::item:selected {{ background: {SELECT}; color: {TEXT}; }}
QHeaderView::section {{ background: {TOOLBAR}; border: 0; border-right: 1px solid {BORDER_SOFT}; border-bottom: 1px solid {BORDER_SOFT};
                       padding: 3px 8px; color: {MUTED}; }}

/* Windows-7-style group headers in Pages */
#GroupTitle {{ color: {ACCENT_TEXT}; font-size: 11pt; }}
#GroupRule {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {SELECT_BORDER}, stop:1 transparent); max-height: 1px; min-height: 1px; }}

/* details pane and status bar */
#DetailsPane {{ background: {TOOLBAR}; border-top: 1px solid {BORDER_SOFT}; }}
#Key {{ color: {MUTED}; font-size: 8pt; }}
QStatusBar {{ background: {TOOLBAR}; border-top: 1px solid {BORDER_SOFT}; color: {MUTED}; }}
QStatusBar QLabel {{ color: {MUTED}; }}
QStatusBar::item {{ border: 0; }}

/* canvas, placeholder, hints */
#Canvas {{ background: {CANVAS}; }}
#Hint {{ color: {MUTED}; font-size: 8pt; }}
#BigTitle {{ font-size: 16pt; font-weight: 300; }}
#Verdict[kind="bad"] {{ background: {DANGER_SOFT}; border: 1px solid {DANGER}; border-radius: 3px; padding: 6px; }}
#Verdict[kind="good"] {{ background: {OK_SOFT}; border: 1px solid {OK}; border-radius: 3px; padding: 6px; }}
QProgressBar {{ border: 1px solid {BORDER_STRONG}; border-radius: 2px; background: #eeeeee; text-align: center; min-height: 14px; }}
QProgressBar::chunk {{ background: {PROGRESS}; }}

/* toast (Windows 7 notification balloon) */
#Toast {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #fff5f8);
          border: 1px solid {BORDER_STRONG}; border-radius: 4px; }}
#ToastTitle {{ font-weight: 600; }}
"""


def apply(app) -> None:
    """Apply the theme to a QApplication."""
    from PySide6.QtGui import QColor, QPalette
    app.setStyle("Fusion")  # a neutral base, so the stylesheet looks the same on every OS
    pal = app.palette()
    # Anything the stylesheet doesn't reach (like tree branch areas) highlights pink, not Fusion blue.
    pal.setColor(QPalette.Highlight, QColor(SELECT_BORDER))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
