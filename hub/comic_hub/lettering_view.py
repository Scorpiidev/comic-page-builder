"""
The Lettering screen: your fonts, a real-size preview, the size advisor,
and the calibration sheet that turns a test print into project presets.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSettings, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QRadioButton, QScrollArea, QSlider, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from cpb_core.lettering import (FontChoice, FontInfo, LetteringPreset, ROLES, TARGETS, build_sheet, cap_height_mm,
                                recommend_pt, scan_fonts, verdict, working_pt)
from cpb_core.lettering.calibration import MAX_FONTS, PAPERS, CalibrationSheet
from cpb_core.project import Project, set_lettering_preset

from . import icons, theme

ROLE_LABELS = {"dialogue": "Dialogue", "caption": "Caption", "whisper": "Whisper", "sfx": "SFX"}
SAMPLE_TEXT = "This is how big your letters print. Can you read me?"


@dataclass(frozen=True)
class FontEntry:
    info: FontInfo
    cap_ratio: float
    measured: bool  # True when Qt measured the cap height because the file didn't say

    @property
    def key(self) -> str:
        return self.info.key

    def choice(self) -> FontChoice:
        return FontChoice(self.info.family, self.info.style, round(self.cap_ratio, 4), self.info.ps_name)


class FontLibrary:
    """
    Installed fonts with their cap heights.

    The cap height comes from the font file (cpb_core reads it). Older fonts
    don't store it, so for those Qt draws an "H" and measures it.
    Favourites are yours, not a project's, so they live in the hub's settings.
    """

    def __init__(self, settings: QSettings, dirs: list[tuple[str, bool]] | None = None, cache_path: str | None = None):
        self.settings = settings
        self.dirs = dirs  # None: the system's font folders
        if cache_path is None:
            folder = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.path.expanduser("~")
            cache_path = os.path.join(folder, "font-cache.json")
        self.cache_path = cache_path
        self.entries: list[FontEntry] = []
        self.errors: list[tuple[str, str]] = []
        self._loaded = False

    def load(self, force: bool = False) -> None:
        """Scan once per session (the cache makes later starts quick); ``force`` rescans."""
        if self._loaded and not force:
            return
        result = scan_fonts(self.dirs, cache_path=self.cache_path)
        entries = []
        for fi in result.fonts:
            ratio, measured = fi.cap_ratio, False
            if ratio is None:
                ratio, measured = self._measure(fi), True
            if ratio and 0.2 <= ratio <= 1.2:  # anything else is a symbol or broken font
                entries.append(FontEntry(fi, ratio, measured))
        self.entries, self.errors, self._loaded = entries, result.errors, True

    @staticmethod
    def _measure(fi: FontInfo) -> float | None:
        cap = QFontMetricsF(font_for(fi, 100, pixel=True)).capHeight()
        return cap / 100 if cap > 0 else None

    # favourites
    def favorites(self) -> set[str]:
        raw = self.settings.value("fonts/favorites", "[]")
        try:
            return set(json.loads(raw)) if isinstance(raw, str) else set(raw or [])
        except ValueError:
            return set()

    def set_favorite(self, key: str, on: bool) -> None:
        fav = self.favorites()
        (fav.add if on else fav.discard)(key)
        self.settings.setValue("fonts/favorites", json.dumps(sorted(fav)))

    def find(self, family: str, style: str) -> FontEntry | None:
        return next((e for e in self.entries if e.info.family == family and e.info.style == style), None)


_families: set[str] = set()   # what Qt can draw, filled on first use
_registered: set[str] = set()  # font files we handed to Qt ourselves


def font_for(info: FontInfo, size: float, pixel: bool = False) -> QFont:
    """A QFont that draws this face. ``size`` is in points, or in pixels with ``pixel``."""
    if not _families:
        _families.update(QFontDatabase.families())
    family = info.family
    if family not in _families:
        if info.legacy_family in _families:
            # Some systems list a face under its older family name ("Comic Neue Light").
            family = info.legacy_family
        elif info.path not in _registered:
            # Qt hasn't seen this file (installed after the hub started, say), so hand it over.
            _registered.add(info.path)
            fid = QFontDatabase.addApplicationFont(info.path)
            _families.update(QFontDatabase.applicationFontFamilies(fid))
    f = QFont(family)
    # Weight and slant first: if Qt can't match the style name, they still pick the closest face.
    f.setWeight(QFont.Weight(max(100, min(900, info.weight))))
    f.setItalic(info.italic)
    f.setStyleName(info.style)
    if pixel:
        f.setPixelSize(max(1, round(size)))
    else:
        f.setPointSizeF(size)
    return f


# ---------------------------------------------------------------------------
class LetterPreview(QWidget):
    """A panel with one speech balloon, drawn at real print size (or zoomed)."""

    note_changed = Signal(str)  # "" at full size, else how much the balloon was shrunk to fit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Canvas")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(260)
        self.info: FontInfo | None = None
        self.size_pt, self.zoom, self.text = 8.5, 2.0, SAMPLE_TEXT

    def set_sample(self, info: FontInfo | None, size_pt: float = 8.5, zoom: float = 1.0, text: str = "") -> None:
        self.info, self.size_pt, self.zoom, self.text = info, size_pt, zoom, text.strip() or " "
        self.note_changed.emit(self.scaled_note())
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.note_changed.emit(self.scaled_note())

    def _geometry(self):
        """Font, text block and balloon size in screen pixels, and how much it must shrink to fit."""
        # A point is 1/72 inch on screen too (Qt uses the screen's logical DPI), so
        # zoom × the print size in points draws the text at zoom × its printed size.
        f = font_for(self.info, self.size_pt * self.zoom)
        size_px = self.size_pt * self.zoom * self.logicalDpiY() / 72
        text = self.text.upper()  # comics are lettered in caps
        block = QFontMetricsF(f, self).boundingRect(QRectF(0, 0, size_px * 11, 1e6), Qt.AlignCenter | Qt.TextWordWrap, text)
        # An ellipse through the corners of the text block, plus breathing room.
        a = block.width() / math.sqrt(2) + size_px * 0.9
        b = block.height() / math.sqrt(2) + size_px * 0.7
        need_w, need_h = 2 * a + 40, 2 * b + b * 0.9 + 50
        scale = min(1.0, (self.width() - 20) / need_w, (self.height() - 20) / need_h)
        return f, text, block, a, b, need_w, need_h, size_px, scale

    def scaled_note(self) -> str:
        if not self.info:
            return ""
        scale = self._geometry()[-1]
        return "" if scale >= 0.999 else f"Shrunk to fit: {scale * self.zoom * 100:.0f}% of print size"

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.CANVAS))
        if not self.info:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "Pick a font")
            return
        p.setRenderHint(QPainter.Antialiasing)
        f, text, block, a, b, need_w, need_h, size_px, scale = self._geometry()
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(scale, scale)
        panel = QRectF(-need_w / 2, -need_h / 2, need_w, need_h)
        p.fillRect(panel, QColor("#ffffff"))
        p.setPen(QPen(QColor("#1b1b1b"), 3))
        p.drawRect(panel)
        cx, cy = 0.0, panel.top() + 20 + b
        ang, hw = math.radians(118), math.radians(11)  # where the tail leaves the body, and half its width
        p1 = QPointF(cx + a * math.cos(ang - hw), cy + b * math.sin(ang - hw))
        p2 = QPointF(cx + a * math.cos(ang + hw), cy + b * math.sin(ang + hw))
        tip = QPointF(cx - a * 0.55, cy + b * 1.9)
        # Body and tail as one outline, like the real balloons: no stroke across the joint.
        # Qt counts arc angles anticlockwise on screen, hence the minus signs.
        path = QPainterPath(p2)
        path.arcTo(QRectF(cx - a, cy - b, 2 * a, 2 * b), -math.degrees(ang + hw), -(360 - math.degrees(2 * hw)))
        path.quadTo(QPointF((p1.x() + tip.x()) / 2 + 6, (p1.y() + tip.y()) / 2), tip)
        path.quadTo(QPointF((p2.x() + tip.x()) / 2 + 2, (p2.y() + tip.y()) / 2), p2)
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor("#1b1b1b"), max(1.0, size_px * 0.08)))
        p.drawPath(path)
        p.setFont(f)
        p.setPen(QColor("#1b1b1b"))
        p.drawText(QRectF(cx - block.width() / 2, cy - block.height() / 2, block.width(), block.height()),
                   Qt.AlignCenter | Qt.TextWordWrap, text)


# ---------------------------------------------------------------------------
class LetteringView(QWidget):
    status_changed = Signal()

    def __init__(self, settings: QSettings, library: FontLibrary | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.library = library or FontLibrary(settings)
        self.project: Project | None = None
        self.entry: FontEntry | None = None
        self.role = "dialogue"
        self.user_pt: float | None = None
        self.favorites_only = False
        self.filter = ""

        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        split = QSplitter(Qt.Horizontal); split.setChildrenCollapsible(False)
        lay.addWidget(split)

        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Name", "Style", "Cap height", "Dialogue size"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 28)
        self.table.cellClicked.connect(self._cell_clicked)
        self.table.itemSelectionChanged.connect(self._row_selected)
        ll.addWidget(self.table, 3)
        prev = QWidget(); pl = QVBoxLayout(prev); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
        self.preview = LetterPreview()
        pl.addWidget(self.preview, 1)
        bar = QWidget(); bar.setObjectName("DetailsPane"); bar.setAttribute(Qt.WA_StyledBackground, True)
        bl = QHBoxLayout(bar); bl.setContentsMargins(12, 4, 12, 4)
        self.sample_text = QLineEdit(SAMPLE_TEXT)
        self.zoom = QComboBox()
        for label, z in (("100% (print size)", 1.0), ("200%", 2.0), ("300%", 3.0)):
            self.zoom.addItem(label, z)
        self.zoom.setCurrentIndex(1)
        self.scaled = QLabel(); self.scaled.setObjectName("Hint")
        bl.addWidget(QLabel("Text:")); bl.addWidget(self.sample_text, 1); bl.addWidget(QLabel("Zoom:")); bl.addWidget(self.zoom)
        bl.addWidget(self.scaled)
        pl.addWidget(bar)
        ll.addWidget(prev, 2)
        split.addWidget(left)

        side = QScrollArea(); side.setWidgetResizable(True); side.setMinimumWidth(360); side.setMaximumWidth(420)
        side.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # the labels wrap instead
        panel = QWidget(); sl = QVBoxLayout(panel); sl.setContentsMargins(12, 8, 12, 12)
        side.setWidget(panel)
        split.addWidget(side)
        split.setStretchFactor(0, 1)

        tg = QGroupBox("Print target"); tf = QFormLayout(tg)
        self.target = QLabel(); self.target.setObjectName("Hint"); self.target.setWordWrap(True)
        self.scale = QComboBox()
        for n, label in ((1, "1× (print size)"), (2, "2×"), (3, "3×")):
            self.scale.addItem(label, n)
        tf.addRow(self.target); tf.addRow("You draw at:", self.scale)
        sl.addWidget(tg)

        rg = QGroupBox("Text role"); rl = QHBoxLayout(rg)
        self.roles = QButtonGroup(self)
        for r in ROLES:
            b = QRadioButton(ROLE_LABELS[r]); b.setProperty("role", r); b.setChecked(r == "dialogue")
            self.roles.addButton(b); rl.addWidget(b)
        sl.addWidget(rg)

        zg = QGroupBox("Size"); zl = QVBoxLayout(zg)
        top = QHBoxLayout()
        self.big = QLabel(); self.big.setObjectName("BigSize")
        self.rec = QLabel(); self.rec.setObjectName("Hint")
        top.addWidget(self.big); top.addWidget(self.rec, 1, Qt.AlignBottom)
        zl.addLayout(top)
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(8, 48)  # half points: 4 to 24 pt
        self.spin = QDoubleSpinBox(); self.spin.setRange(4, 24); self.spin.setSingleStep(0.5); self.spin.setDecimals(1); self.spin.setSuffix(" pt")
        row.addWidget(QLabel("Your size:")); row.addWidget(self.slider, 1); row.addWidget(self.spin)
        zl.addLayout(row)
        self.cap_line = QLabel(); self.cap_line.setObjectName("Hint"); self.cap_line.setWordWrap(True)
        self.verdict = QLabel(); self.verdict.setObjectName("Verdict"); self.verdict.setWordWrap(True)
        self.verdict.setMargin(5)  # keeps the text off the coloured border
        zl.addWidget(self.cap_line); zl.addWidget(self.verdict)
        btns = QHBoxLayout()
        self.use_rec = QPushButton("Use recommended"); self.save_preset = QPushButton(icons.icon("check"), "Save as preset")
        self.save_preset.setToolTip("Make this font and size the project's size for this kind of text")
        self.save_preset.setDefault(True)
        btns.addWidget(self.use_rec); btns.addWidget(self.save_preset)
        zl.addLayout(btns)
        sl.addWidget(zg)

        pg = QGroupBox("Project lettering"); self.presets_lay = QFormLayout(pg)
        sl.addWidget(pg)
        sl.addStretch()

        self.scale.currentIndexChanged.connect(self._scale_changed)
        self.roles.buttonClicked.connect(self._role_changed)
        self.slider.valueChanged.connect(lambda v: self._size_changed(v / 2))
        self.spin.valueChanged.connect(self._size_changed)
        self.use_rec.clicked.connect(self._use_recommended)
        self.save_preset.clicked.connect(self._save_preset)
        self.sample_text.textChanged.connect(lambda _: self._show())
        self.zoom.currentIndexChanged.connect(lambda _: self._show())
        self.preview.note_changed.connect(self.scaled.setText)

    # ---------- data ----------
    def set_project(self, project: Project) -> None:
        self.project = project
        self.library.load()
        self.scale.blockSignals(True)
        self.scale.setCurrentIndex(max(0, min(2, project.work_scale - 1)))
        self.scale.blockSignals(False)
        preset = project.lettering.get(self.role)
        if self.entry is None and preset:
            self.entry = self.library.find(preset.family, preset.style)
            self.user_pt = preset.size_pt
        self.refresh_table()

    def visible_entries(self) -> list[FontEntry]:
        fav, q = self.library.favorites(), self.filter.strip().lower()
        return [e for e in self.library.entries if (not self.favorites_only or e.key in fav)
                and (not q or q in f"{e.info.family} {e.info.style}".lower())]

    def refresh_table(self) -> None:
        fav = self.library.favorites()
        rows = self.visible_entries()
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        self._rows = rows
        select = None
        for r, e in enumerate(rows):
            star = QTableWidgetItem(); star.setIcon(icons.icon("star", theme.ACCENT if e.key in fav else theme.BORDER_SOFT))
            star.setToolTip("Click to add to or remove from favourites")
            name = QTableWidgetItem(e.info.family)
            name.setFont(font_for(e.info, 11))
            cap = QTableWidgetItem(f"{e.cap_ratio:.2f} em" + (" (measured)" if e.measured else ""))
            if e.measured:
                cap.setToolTip("This font file doesn't store its cap height, so the hub measured an H.")
            size = QTableWidgetItem(f"{recommend_pt(e.cap_ratio, 'dialogue'):g} pt")
            for c, it in enumerate((star, name, QTableWidgetItem(e.info.style), cap, size)):
                self.table.setItem(r, c, it)
            if self.entry and e.key == self.entry.key:
                select = r
        self.table.blockSignals(False)
        if select is not None:
            self.table.selectRow(select)
        elif rows and not self.entry:
            self.table.selectRow(0)
        self._show()

    def _cell_clicked(self, row: int, col: int) -> None:
        if col == 0:
            e = self._rows[row]
            self.library.set_favorite(e.key, e.key not in self.library.favorites())
            self.refresh_table()

    def _row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.entry = self._rows[rows[0].row()]
            self.user_pt = None
            self._show()

    # ---------- advisor ----------
    def recommended(self) -> float | None:
        return recommend_pt(self.entry.cap_ratio, self.role) if self.entry else None

    def size(self) -> float | None:
        return self.user_pt if self.user_pt is not None else self.recommended()

    def _scale_changed(self, _i: int) -> None:
        if self.project:
            self.project.work_scale = self.scale.currentData()
            self.project.save()
        self._show()

    def _role_changed(self, button) -> None:
        self.role = button.property("role")
        preset = self.project.lettering.get(self.role) if self.project else None
        self.user_pt = preset.size_pt if preset and self.entry and preset.family == self.entry.info.family else None
        self._show()

    def _size_changed(self, value: float) -> None:
        value = round(value * 2) / 2
        if self.entry and value != self.size():
            self.user_pt = value
            self._show()

    def _use_recommended(self) -> None:
        self.user_pt = None
        self._show()

    def _save_preset(self) -> None:
        if not (self.project and self.entry):
            return
        e, pt = self.entry, self.size()
        set_lettering_preset(self.project, self.role, LetteringPreset(e.info.family, e.info.style, pt, round(e.cap_ratio, 4), e.info.ps_name))
        self.window().toast("Preset saved", f"{e.info.family} {e.info.style} at {pt:g} pt is now {self.project.name}'s "
                                            f"{ROLE_LABELS[self.role].lower()} size.")
        self._show()

    def _show(self) -> None:
        p = self.project
        if p:
            self.target.setText(f"{p.paper} · {p.size.trim_w:g} × {p.size.trim_h:g} mm trim (from {p.name})")
        _clear_form(self.presets_lay)
        for r in ROLES:
            pr = p.lettering.get(r) if p else None
            self.presets_lay.addRow(QLabel(ROLE_LABELS[r] + ":"),
                                    QLabel(f"{pr.family} {pr.style} · {pr.size_pt:g} pt ({pr.cap_mm:.2f} mm)" if pr else "not set yet"))
        e = self.entry
        for w in (self.slider, self.spin, self.use_rec, self.save_preset):
            w.setEnabled(e is not None)
        if not e:
            self.big.setText("–"); self.rec.setText(""); self.cap_line.setText(""); self.verdict.setText("")
            self.preview.set_sample(None)
            self.status_changed.emit()
            return
        pt, rec = self.size(), self.recommended()
        for w, v in ((self.slider, round(pt * 2)), (self.spin, pt)):
            w.blockSignals(True); w.setValue(v); w.blockSignals(False)
        self.big.setText(f"{pt:g} pt")
        self.rec.setText("recommended, at print size" if pt == rec else f"recommended: {rec:g} pt")
        cap = cap_height_mm(pt, e.cap_ratio)
        scale = self.scale.currentData()
        self.cap_line.setText(f"{cap:.2f} mm cap height when printed · type {working_pt(pt, scale):g} pt in your "
                              f"{scale}× canvas · target {TARGETS[self.role]} mm")
        kind, msg = verdict(cap, self.role)
        self.verdict.setText(msg)
        self.verdict.setProperty("kind", kind)  # bad, small or good: the theme colours each
        self.verdict.style().unpolish(self.verdict); self.verdict.style().polish(self.verdict)
        self.preview.set_sample(e.info, pt, self.zoom.currentData(), self.sample_text.text())
        self.status_changed.emit()

    def status_text(self) -> str:
        fav = len(self.library.favorites())
        if not self.entry:
            return f"{len(self.library.entries)} fonts · {fav} favourites"
        return (f"{len(self.library.entries)} fonts · {fav} favourites · {self.entry.info.family} {self.entry.info.style} "
                f"at {self.size():g} pt for {ROLE_LABELS[self.role].lower()}")


def _clear_form(form: QFormLayout) -> None:
    while form.rowCount():
        form.removeRow(0)


# ---------------------------------------------------------------------------
class CalibrationDialog(QDialog):
    """
    Step 1: make the sheet (pick up to three fonts, a role and a paper; save the PDF).
    Step 2: after printing, type the code of the sample that read best; it becomes the preset.
    The last sheet's choices are remembered, so the codes still match when you come back.
    """

    def __init__(self, view: LetteringView, parent=None):
        super().__init__(parent)
        self.view, self.project, self.library = view, view.project, view.library
        self.setWindowTitle("Calibration sheet")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)

        g1 = QGroupBox("1 · Make the sheet"); f1 = QVBoxLayout(g1)
        f1.addWidget(_hint(f"Pick up to {MAX_FONTS} fonts. Each gets six samples around its recommended size. "
                           "Your favourites are listed here: star fonts on the Lettering screen to add them."))
        self.fonts = QListWidget(); self.fonts.setMaximumHeight(150)
        last = self._last()
        wanted = {(c["family"], c["style"]) for c in last.get("fonts", [])}
        fav = self.library.favorites()
        candidates = [e for e in self.library.entries if e.key in fav or (view.entry and e.key == view.entry.key)
                      or (e.info.family, e.info.style) in wanted]
        if not candidates and view.entry:
            candidates = [view.entry]
        for e in candidates:
            it = QListWidgetItem(f"{e.info.family} {e.info.style}  ·  caps {e.cap_ratio:.2f} em")
            it.setData(Qt.UserRole, e.key)
            on = (e.info.family, e.info.style) in wanted if wanted else (view.entry is not None and e.key == view.entry.key)
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.fonts.addItem(it)
        f1.addWidget(self.fonts)
        row = QHBoxLayout()
        self.role = QComboBox()
        for r in ROLES:
            self.role.addItem(ROLE_LABELS[r], r)
        self.role.setCurrentIndex(ROLES.index(last.get("role", view.role)))
        self.paper = QComboBox()
        for name in PAPERS:
            self.paper.addItem(name)
        self.paper.setCurrentText(last.get("paper", "A4"))
        row.addWidget(QLabel("Role:")); row.addWidget(self.role); row.addSpacing(12)
        row.addWidget(QLabel("Paper:")); row.addWidget(self.paper); row.addStretch()
        f1.addLayout(row)
        self.save_pdf = QPushButton(icons.icon("send"), "Save PDF and open it…")
        f1.addWidget(self.save_pdf)
        lay.addWidget(g1)

        g2 = QGroupBox("2 · After printing"); f2 = QFormLayout(g2)
        f2.addRow(_hint("Print at 100% and check the 100 mm bar. Then type the code of the smallest sample "
                        "that reads comfortably at arm's length."))
        self.code = QLineEdit(); self.code.setPlaceholderText("e.g. A4"); self.code.setMaxLength(3)
        self.meaning = QLabel(); self.meaning.setObjectName("Hint")
        f2.addRow("Best sample:", self.code); f2.addRow(self.meaning)
        lay.addWidget(g2)

        btns = QHBoxLayout(); btns.addStretch()
        self.use = QPushButton("Save as project preset"); self.use.setDefault(True); self.use.setEnabled(False)
        close = QPushButton("Close")
        btns.addWidget(self.use); btns.addWidget(close)
        lay.addLayout(btns)

        self.save_pdf.clicked.connect(self._save_pdf)
        self.code.textChanged.connect(self._code_changed)
        self.use.clicked.connect(self._use)
        close.clicked.connect(self.reject)
        self.fonts.itemChanged.connect(lambda _: self._code_changed(self.code.text()))
        self.role.currentIndexChanged.connect(lambda _: self._code_changed(self.code.text()))

    def _last(self) -> dict:
        try:
            return json.loads(self.view.settings.value("calibration/last", "{}"))
        except (TypeError, ValueError):
            return {}

    def chosen(self) -> list[FontEntry]:
        keys = [self.fonts.item(i).data(Qt.UserRole) for i in range(self.fonts.count())
                if self.fonts.item(i).checkState() == Qt.Checked]
        by_key = {e.key: e for e in self.library.entries}
        return [by_key[k] for k in keys if k in by_key]

    def sheet(self) -> CalibrationSheet:
        return build_sheet([e.choice() for e in self.chosen()], role=self.role.currentData(),
                           paper=self.paper.currentText(), title=f"Lettering calibration · {self.project.name}")

    def default_path(self) -> str:
        sub = "exports" if "exports" in self.project.folders else ""
        folder = os.path.join(self.project.folder, sub)
        return os.path.join(folder, f"lettering_calibration_{self.role.currentData()}.pdf")

    def _save_pdf(self) -> None:
        try:
            sheet = self.sheet()
        except ValueError as e:
            QMessageBox.warning(self, "Can't make the sheet", str(e).capitalize() + ".")
            return
        os.makedirs(os.path.dirname(self.default_path()), exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save the calibration sheet", self.default_path(), "PDF (*.pdf)")
        if not path:
            return
        self.write_pdf(sheet, path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))  # straight to your PDF viewer, ready to print

    def write_pdf(self, sheet: CalibrationSheet, path: str) -> None:
        from .calibration_pdf import render_sheet_pdf
        by_name = {(e.info.family, e.info.style): e for e in self.library.entries}

        def qfont(choice: FontChoice, size_pt: float) -> QFont:
            e = by_name.get((choice.family, choice.style))
            if e:
                return font_for(e.info, size_pt)
            f = QFont(choice.family); f.setStyleName(choice.style); f.setPointSizeF(size_pt)
            return f

        render_sheet_pdf(sheet, path, qfont)
        self.view.settings.setValue("calibration/last", json.dumps({
            "fonts": [{"family": f.family, "style": f.style} for _l, f, _y in sheet.fonts],
            "role": sheet.role, "paper": sheet.paper}))
        self.view.window().toast("Calibration sheet saved", f"{os.path.basename(path)}: print it at 100% and pick the best sample.")

    def _code_changed(self, text: str) -> None:
        self.use.setEnabled(False)
        if not text.strip():
            self.meaning.setText("")
            return
        try:
            s = self.sheet().sample(text)
        except (KeyError, ValueError):
            self.meaning.setText("No sample with that code on this sheet.")
            return
        self.meaning.setText(f"{s.font.family} {s.font.style} · {s.size_pt:g} pt · {s.cap_mm:.2f} mm caps")
        self.use.setEnabled(True)

    def _use(self) -> None:
        s = self.sheet().sample(self.code.text())
        role = self.role.currentData()
        set_lettering_preset(self.project, role, LetteringPreset(s.font.family, s.font.style, s.size_pt, s.font.cap_ratio, s.font.ps_name))
        self.view.window().toast("Preset saved", f"{s.font.family} {s.font.style} at {s.size_pt:g} pt is now the {ROLE_LABELS[role].lower()} size.")
        self.view.entry = self.library.find(s.font.family, s.font.style) or self.view.entry
        self.view.role, self.view.user_pt = role, s.size_pt
        for b in self.view.roles.buttons():
            b.setChecked(b.property("role") == role)
        self.view.refresh_table()
        self.accept()


def _hint(text: str) -> QLabel:
    lab = QLabel(text); lab.setObjectName("Hint"); lab.setWordWrap(True)
    return lab
