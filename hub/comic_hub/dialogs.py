"""Dialogs: new project / project settings, add page, batch generate, layout options."""

from __future__ import annotations

import os
import random
from dataclasses import replace

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMessageBox,
    QProgressBar, QPushButton, QRadioButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from cpb_core.build import page_from_bsp, page_from_preset, plan_batch
from cpb_core.geometry import PageSize
from cpb_core.layouts.presets import load_presets
from cpb_core.model import Page
from cpb_core.paper import PAPER_SIZES
from cpb_core.project import FOLDERS, STATUSES, Project

from . import icons, theme
from .widgets import UnitSpinBox, page_thumbnail

PRESET_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "comicpagebuilder", "resources", "layouts")
MODES = [("auto", "Auto (cut the longer side)"), ("rows", "Rows only"), ("cols", "Columns only"), ("chaos", "Chaos")]


def _hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("Hint")
    lab.setWordWrap(True)
    return lab


def _status_combo(current: str = "thumbs") -> QComboBox:
    c = QComboBox()
    for s in STATUSES:
        c.addItem(theme.STATUS_LABELS[s], s)
    c.setCurrentIndex(STATUSES.index(current))
    return c


def _header(title: str, subtitle: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 4)
    face = QLabel()
    face.setPixmap(icons.mascot(40))
    col = QVBoxLayout()
    t = QLabel(title)
    t.setObjectName("GroupTitle")
    col.addWidget(t)
    col.addWidget(_hint(subtitle))
    lay.addWidget(face)
    lay.addLayout(col, 1)
    return w


# ---------------------------------------------------------------------------
class ProjectDialog(QDialog):
    """
    New project wizard (General, Page setup, Folders & pages), or the same
    tabs as Project settings for the open project.
    """

    def __init__(self, parent=None, project: Project | None = None):
        super().__init__(parent)
        self.settings_mode = project is not None
        self.setWindowTitle(f"Project settings · {project.name}" if project else "New project")
        self.setMinimumWidth(500)
        p = project
        lay = QVBoxLayout(self)
        lay.addWidget(_header(p.name if p else "Set up a new comic",
                              "Changes apply to new pages. Existing pages keep their size." if p
                              else "You can change all of this later in Project settings."))
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        # General
        g = QWidget(); f = QFormLayout(g)
        self.name = QLineEdit(p.name if p else "Untitled Comic")
        self.folder = QLineEdit(p.folder if p else os.path.join(os.path.expanduser("~"), "Comics", "Untitled Comic"))
        self.folder.setReadOnly(self.settings_mode)
        browse = QPushButton("Browse…"); browse.setEnabled(not self.settings_mode); browse.clicked.connect(self._browse)
        row = QHBoxLayout(); row.addWidget(self.folder, 1); row.addWidget(browse)
        self.chapter = QLineEdit(p.chapter if p else "Chapter 1")
        self.ltr, self.rtl = QRadioButton("Left to right"), QRadioButton("Right to left (manga)")
        (self.rtl if p and p.reading == "rtl" else self.ltr).setChecked(True)
        rr = QHBoxLayout(); rr.addWidget(self.ltr); rr.addWidget(self.rtl); rr.addStretch()
        f.addRow("Name:", self.name); f.addRow("Location:", row); f.addRow("First chapter:", self.chapter)
        f.addRow("Reading order:", rr)
        if not self.settings_mode:
            self.name.textEdited.connect(self._name_to_folder)
        self.tabs.addTab(g, "General")

        # Page setup
        s = QWidget(); f2 = QFormLayout(s)
        size = p.size if p else PageSize(168, 260)
        self.paper = QComboBox()
        for name in PAPER_SIZES:
            self.paper.addItem(name)
        self.paper.addItem("Custom")
        self.paper.setCurrentText(p.paper if p and (p.paper in PAPER_SIZES or p.paper == "Custom") else "US Comic")
        self.trim_w = UnitSpinBox(size.trim_w, 20, 1000); self.trim_h = UnitSpinBox(size.trim_h, 20, 1000)
        self.bleed = UnitSpinBox(size.bleed, 0, 50); self.safe = UnitSpinBox(size.safe, 0, 50)
        self.margin = UnitSpinBox(size.margin, 0, 80)
        self.dpi = QSpinBox(); self.dpi.setRange(72, 2400); self.dpi.setValue(size.dpi); self.dpi.setSuffix(" dpi")
        self.scale = QComboBox()
        for n, label in ((1, "1× (print size)"), (2, "2×"), (3, "3×")):
            self.scale.addItem(label, n)
        self.scale.setCurrentIndex((p.work_scale if p else 2) - 1)
        self.paper.currentTextChanged.connect(self._paper_changed)
        self.trim_w.mmChanged.connect(lambda _: self._custom()); self.trim_h.mmChanged.connect(lambda _: self._custom())
        f2.addRow("Page size:", self.paper)
        trim = QHBoxLayout(); trim.addWidget(self.trim_w); trim.addWidget(QLabel("×")); trim.addWidget(self.trim_h)
        f2.addRow("Trim:", trim); f2.addRow("Bleed:", self.bleed); f2.addRow("Safe area:", self.safe)
        f2.addRow("Panel margin:", self.margin); f2.addRow("Resolution:", self.dpi); f2.addRow("You draw at:", self.scale)
        f2.addRow(_hint("These become the defaults for every new page. The lettering advisor uses the print size."))
        self.tabs.addTab(s, "Page setup")

        # Folders & pages
        fw = QWidget(); fl = QVBoxLayout(fw)
        fl.addWidget(_hint("Folders created inside the project location:"))
        self.folder_checks = {}
        for name in FOLDERS:
            c = QCheckBox(name.capitalize() + ("  (required)" if name == "pages" else ""))
            c.setChecked(name in (p.folders if p else FOLDERS))
            c.setEnabled(name != "pages")
            self.folder_checks[name] = c
            fl.addWidget(c)
        self.blank = QSpinBox(); self.blank.setRange(0, 50); self.blank.setValue(8); self.blank.setSuffix(" blank pages")
        if not self.settings_mode:
            fr = QHBoxLayout(); fr.addWidget(QLabel("Start with:")); fr.addWidget(self.blank); fr.addStretch()
            fl.addLayout(fr)
        fl.addStretch()
        self.tabs.addTab(fw, "Folders && pages")

        # Buttons: Back / Next / Create in wizard mode, OK / Cancel in settings mode.
        btns = QHBoxLayout(); btns.addStretch()
        self.back = QPushButton("< Back"); self.next = QPushButton("Next >"); self.ok = QPushButton("Create project" if not p else "OK")
        cancel = QPushButton("Cancel")
        for b in (self.back, self.next):
            b.setVisible(not self.settings_mode)
        for b in (self.back, self.next, self.ok, cancel):
            btns.addWidget(b)
        lay.addLayout(btns)
        self.back.clicked.connect(lambda: self._step(-1)); self.next.clicked.connect(lambda: self._step(1))
        self.ok.clicked.connect(self._accept); cancel.clicked.connect(self.reject)
        self.tabs.currentChanged.connect(lambda _: self._refresh())
        self._paper_changed(self.paper.currentText(), initial=True)
        self._refresh()

    # wizard plumbing
    def _step(self, d: int) -> None:
        if d > 0 and not self.name.text().strip():
            QMessageBox.warning(self, "Name needed", "Give the project a name first.")
            return
        self.tabs.setCurrentIndex(self.tabs.currentIndex() + d)

    def _refresh(self) -> None:
        i = self.tabs.currentIndex()
        if not self.settings_mode:
            for t in range(self.tabs.count()):
                self.tabs.setTabEnabled(t, t <= max(i, self._reached()))
            self.back.setEnabled(i > 0)
            self.next.setVisible(i < self.tabs.count() - 1)
            self.ok.setVisible(i == self.tabs.count() - 1)
        (self.ok if self.ok.isVisible() else self.next).setDefault(True)

    def _reached(self) -> int:
        self._max = max(getattr(self, "_max", 0), self.tabs.currentIndex())
        return self._max

    def _name_to_folder(self, text: str) -> None:
        base = os.path.dirname(self.folder.text()) or os.path.expanduser("~")
        self.folder.setText(os.path.join(base, text.strip() or "Untitled Comic"))

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Where should the project folder go?", os.path.dirname(self.folder.text()))
        if d:
            self.folder.setText(os.path.join(d, self.name.text().strip() or "Untitled Comic"))

    def _paper_changed(self, name: str, initial: bool = False) -> None:
        if name in PAPER_SIZES and not (initial and self.settings_mode):
            w, h = PAPER_SIZES[name]
            self._setting = True
            self.trim_w.set_mm(w); self.trim_h.set_mm(h)
            self._setting = False

    def _custom(self) -> None:
        if not getattr(self, "_setting", False) and self.paper.currentText() != "Custom":
            self.paper.blockSignals(True); self.paper.setCurrentText("Custom"); self.paper.blockSignals(False)

    def _accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Name needed", "Give the project a name first.")
            return
        try:
            self.values()  # validates the page size
        except ValueError as e:
            QMessageBox.warning(self, "Check the page setup", str(e).capitalize())
            return
        self.accept()

    def values(self) -> dict:
        """Everything the dialog decided, ready for create_project / update_settings."""
        size = PageSize(trim_w=self.trim_w.mm(), trim_h=self.trim_h.mm(), bleed=self.bleed.mm(),
                        safe=self.safe.mm(), margin=self.margin.mm(), dpi=self.dpi.value())
        return dict(name=self.name.text().strip(), folder=self.folder.text().strip(), chapter=self.chapter.text().strip() or "Chapter 1",
                    reading="rtl" if self.rtl.isChecked() else "ltr", work_scale=self.scale.currentData(),
                    paper=self.paper.currentText(), size=size,
                    folders=tuple(n for n, c in self.folder_checks.items() if c.isChecked()),
                    blank_pages=self.blank.value())


# ---------------------------------------------------------------------------
class AddPageDialog(QDialog):
    wants_batch = Signal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add page")
        lay = QVBoxLayout(self)
        t = QLabel(f"Add page {project.next_number():02d} to {project.name}")
        t.setObjectName("GroupTitle")
        lay.addWidget(t)
        f = QFormLayout()
        self.panels = QSpinBox(); self.panels.setRange(1, 8); self.panels.setValue(5)
        self.mode = QComboBox()
        for key, label in [("auto", "Random, balanced"), ("rows", "Rows"), ("cols", "Columns"), ("chaos", "Chaos")]:
            self.mode.addItem(label, key)
        self.status = _status_combo()
        f.addRow("Panels:", self.panels); f.addRow("Layout:", self.mode); f.addRow("Status:", self.status)
        lay.addLayout(f)
        self.open_builder = QCheckBox("Open it in the Page builder")
        lay.addWidget(self.open_builder)
        btns = QHBoxLayout()
        more = QPushButton("More than one…"); more.clicked.connect(lambda: (self.reject(), self.wants_batch.emit()))
        add = QPushButton("Add page"); add.setDefault(True); add.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(more); btns.addStretch(); btns.addWidget(add); btns.addWidget(cancel)
        lay.addLayout(btns)


# ---------------------------------------------------------------------------
class BatchDialog(QDialog):
    """Generate several pages at once, with a live preview of what you'll get."""

    def __init__(self, project: Project, selected: int | None, parent=None):
        super().__init__(parent)
        self.project, self.selected = project, selected
        self.seed = random.randrange(1, 10**9)
        self.setWindowTitle("Batch generate pages")
        self.setMinimumWidth(540)
        lay = QVBoxLayout(self)

        how = QGroupBox("How many"); hf = QFormLayout(how)
        self.count = QSpinBox(); self.count.setRange(1, 50); self.count.setValue(8); self.count.setSuffix(" pages")
        hf.addRow("Pages:", self.count)
        self.range = _hint(""); hf.addRow(self.range)
        lay.addWidget(how)

        lg = QGroupBox("Layouts"); ll = QVBoxLayout(lg)
        self.modes = QButtonGroup(self)
        same_ok = selected is not None and self._selected_recipe() is not None
        for key, label in [("same", f"Same as the selected page ({selected:02d})" if same_ok else "Same as the selected page"),
                           ("auto", "Random, balanced"), ("mixed", "Random mix of rows, columns and balanced"), ("chaos", "Chaos")]:
            r = QRadioButton(label); r.setProperty("mode", key)
            r.setEnabled(key != "same" or same_ok)
            self.modes.addButton(r); ll.addWidget(r)
            if key == "auto":
                r.setChecked(True)
        pr = QHBoxLayout()
        self.lo = QSpinBox(); self.lo.setRange(1, 8); self.lo.setValue(4)
        self.hi = QSpinBox(); self.hi.setRange(1, 8); self.hi.setValue(6)
        self.panels_label = QLabel("Panels per page:")
        pr.addWidget(self.panels_label); pr.addWidget(self.lo); pr.addWidget(QLabel("to")); pr.addWidget(self.hi); pr.addStretch()
        ll.addLayout(pr)
        lay.addWidget(lg)

        sg = QGroupBox("Setup"); sf = QFormLayout(sg)
        self.status = _status_combo()
        sf.addRow("Start as:", self.status)
        lay.addWidget(sg)

        lay.addWidget(_hint("Preview"))
        self.strip = QListWidget()
        self.strip.setObjectName("Canvas")
        self.strip.setViewMode(QListView.IconMode); self.strip.setFlow(QListView.LeftToRight); self.strip.setWrapping(False)
        self.strip.setIconSize(QSize(44, 66)); self.strip.setFixedHeight(104); self.strip.setSelectionMode(QListWidget.NoSelection)
        self.strip.setStyleSheet(f"QListWidget {{ background: {theme.CANVAS}; border: 1px solid {theme.BORDER_SOFT}; }}")
        lay.addWidget(self.strip)
        self.progress = QProgressBar(); self.progress.hide()
        lay.addWidget(self.progress)

        btns = QHBoxLayout()
        shuffle = QPushButton(icons.icon("dice"), "Shuffle"); shuffle.clicked.connect(self._shuffle)
        self.go = QPushButton(icons.icon("stack"), "Generate pages"); self.go.setDefault(True); self.go.clicked.connect(self._generate)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(shuffle); btns.addStretch(); btns.addWidget(self.go); btns.addWidget(cancel)
        lay.addLayout(btns)

        for w in (self.count, self.lo, self.hi):
            w.valueChanged.connect(self._refresh)
        self.modes.buttonClicked.connect(lambda _: self._refresh())
        self.made: list[Page] = []
        self._refresh()

    def _selected_recipe(self):
        try:
            r = self.project.load_page(self.selected).layout
            return r if r.get("kind") == "bsp" else None
        except Exception:
            return None

    def _mode(self) -> str:
        return self.modes.checkedButton().property("mode")

    def _plan(self):
        same = self._selected_recipe() if self._mode() == "same" else None
        return plan_batch(self.count.value(), mode=self._mode(), min_panels=self.lo.value(), max_panels=self.hi.value(),
                          seed=self.seed, same_as=same)

    def _shuffle(self) -> None:
        self.seed = random.randrange(1, 10**9)
        self._refresh()

    def _refresh(self) -> None:
        start = self.project.next_number()
        n = self.count.value()
        self.range.setText(f"Creates pages {start:02d}" + (f" to {start + n - 1:02d}" if n > 1 else "") +
                           " in the project's Pages folder. Numbering continues after your last page, so nothing is overwritten.")
        same = self._mode() == "same"
        for w in (self.panels_label, self.lo, self.hi):
            w.setEnabled(not same)
        self.strip.clear()
        p = self.project
        for i, r in enumerate(self._plan()[:14]):
            page = page_from_bsp(start + i, p.size, r["panels"], mode=r["mode"], seed=r["seed"], snap=r["snap"],
                                 gutter=p.gutter, reading=p.reading, style=p.style)
            item = QListWidgetItem(QIcon(page_thumbnail(page, 44)), f"{start + i:02d} · {len(page.cells)}p")
            self.strip.addItem(item)
        if n > 14:
            self.strip.addItem(QListWidgetItem(f"+{n - 14} more"))

    def _generate(self) -> None:
        self.go.setEnabled(False)
        self.progress.show(); self.progress.setRange(0, self.count.value()); self.progress.setValue(0)

        def tick(done: int, total: int) -> None:
            self.progress.setValue(done)
            QApplication.processEvents()  # keep the window painting while pages are written

        same = self.selected if self._mode() == "same" else None
        try:
            self.made = self.project.add_batch(self.count.value(), mode=self._mode(), min_panels=self.lo.value(),
                                               max_panels=self.hi.value(), status=self.status.currentData(),
                                               seed=self.seed, same_as=same, progress=tick)
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Batch failed", str(e).capitalize())
            self.go.setEnabled(True)
            return
        self.accept()


# ---------------------------------------------------------------------------
class LayoutOptionsDialog(QDialog):
    """
    Random (BSP) and preset layouts for the page in the builder.

    Every change is sent live with ``changed`` so the preview follows along;
    Cancel sends the original page back.
    """

    changed = Signal(object)  # Page

    def __init__(self, page: Page, parent=None):
        super().__init__(parent)
        self.original = self.page = page
        self.setWindowTitle("Layout options")
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        r = page.layout if page.layout.get("kind") == "bsp" else {"panels": max(1, len(page.cells)), "mode": "auto",
                                                                   "seed": random.randrange(10_000, 100_000), "snap": True}
        self.seed = r["seed"]

        bsp = QWidget(); bl = QVBoxLayout(bsp)
        box = QGroupBox("Randomizer"); bf = QFormLayout(box)
        self.panels = QSpinBox(); self.panels.setRange(1, 8); self.panels.setValue(r["panels"])
        bf.addRow("Panels:", self.panels)
        self.mode_group = QButtonGroup(self)
        modes = QVBoxLayout()
        for key, label in MODES:
            b = QRadioButton(label); b.setProperty("mode", key); b.setChecked(key == r["mode"])
            self.mode_group.addButton(b); modes.addWidget(b)
        bf.addRow("Cut mode:", modes)
        bl.addWidget(box)
        adv = QGroupBox("Advanced settings"); al = QVBoxLayout(adv)
        self.lock = QCheckBox("Lock seed (keep this layout)"); self.lock.setChecked(True)
        self.snap = QCheckBox("Snap cuts to thirds and halves"); self.snap.setChecked(r.get("snap", True))
        self.rtl = QCheckBox("Right-to-left reading order (manga)"); self.rtl.setChecked(page.reading == "rtl")
        self.seed_label = _hint("")
        for w in (self.lock, self.snap, self.rtl, self.seed_label):
            al.addWidget(w)
        bl.addWidget(adv)
        self.tabs.addTab(bsp, "Random")

        pre = QWidget(); pl = QVBoxLayout(pre)
        self.presets = QListWidget()
        self.presets.setViewMode(QListView.IconMode); self.presets.setIconSize(QSize(46, 70))
        self.presets.setResizeMode(QListView.Adjust); self.presets.setMovement(QListView.Static); self.presets.setSpacing(4)
        self.presets.setMinimumHeight(260)
        result = load_presets(PRESET_DIR)
        self._presets = result.presets
        for i, preset in enumerate(result.presets):
            thumb = page_from_preset(page.number, page.size, preset, gutter=page.gutter, style=page.style)
            item = QListWidgetItem(QIcon(page_thumbnail(thumb, 46)), preset.name if len(preset.name) < 14 else preset.name[:12] + "…")
            item.setToolTip(f"{preset.name} · {preset.panel_count} panels")
            item.setData(Qt.UserRole, i)
            self.presets.addItem(item)
            if page.layout == {"kind": "preset", "name": preset.name}:
                item.setSelected(True)
        pl.addWidget(self.presets)
        if result.errors:
            pl.addWidget(_hint("Couldn't read: " + ", ".join(n for n, _ in result.errors)))
        self.tabs.addTab(pre, "Presets")
        self.tabs.addTab(QWidget(), "Grid")
        self.tabs.setTabEnabled(2, False)
        self.tabs.setTabToolTip(2, "The merge grid comes back in a later milestone")
        if page.layout.get("kind") == "preset":
            self.tabs.setCurrentIndex(1)

        btns = QHBoxLayout()
        roll = QPushButton(icons.icon("dice"), "Roll again"); roll.clicked.connect(self._roll)
        ok = QPushButton("OK"); ok.setDefault(True); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(roll); btns.addStretch(); btns.addWidget(ok); btns.addWidget(cancel)
        lay.addLayout(btns)

        self.panels.valueChanged.connect(lambda _: self._bsp_changed(reroll=not self.lock.isChecked()))
        self.mode_group.buttonClicked.connect(lambda _: self._bsp_changed())
        self.snap.toggled.connect(lambda _: self._bsp_changed())
        self.rtl.toggled.connect(lambda _: self._reading_changed())
        self.presets.itemClicked.connect(self._preset_clicked)
        self._update_seed_label()

    def _update_seed_label(self) -> None:
        self.seed_label.setText(f"Seed {self.seed}" + (" (locked: the gutter and page size re-flow this layout instead of re-rolling it)"
                                                       if self.lock.isChecked() else ""))

    def _emit(self, page: Page) -> None:
        self.page = page
        self.changed.emit(page)

    def _bsp_changed(self, reroll: bool = False) -> None:
        if reroll:
            self.seed = random.randrange(10_000, 100_000)
        p = self.page
        mode = self.mode_group.checkedButton().property("mode")
        self._emit(page_from_bsp(p.number, p.size, self.panels.value(), mode=mode, seed=self.seed, snap=self.snap.isChecked(),
                                 gutter=p.gutter, reading="rtl" if self.rtl.isChecked() else "ltr", style=p.style))
        self._update_seed_label()

    def _roll(self) -> None:
        self.tabs.setCurrentIndex(0)
        self._bsp_changed(reroll=True)

    def _reading_changed(self) -> None:
        self._emit(replace(self.page, reading="rtl" if self.rtl.isChecked() else "ltr"))

    def _preset_clicked(self, item: QListWidgetItem) -> None:
        preset = self._presets[item.data(Qt.UserRole)]
        p = self.page
        self._emit(page_from_preset(p.number, p.size, preset, gutter=p.gutter,
                                    reading="rtl" if self.rtl.isChecked() else "ltr", style=p.style))

    def reject(self) -> None:
        self.changed.emit(self.original)
        super().reject()
