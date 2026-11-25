"""The screens inside the main window: Projects, Pages, Page builder, placeholders."""

from __future__ import annotations

import os
from dataclasses import replace

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QListView, QListWidget, QListWidgetItem, QPushButton, QRadioButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from cpb_core.build import page_manual, rebuild
from cpb_core.geometry import PageSize
from cpb_core.model import Page, PanelStyle
from cpb_core.paper import PAPER_SIZES
from cpb_core.project import STATUSES, Project, load_project

from . import icons, theme
from .layout_canvas import LayoutCanvas
from .widgets import GroupHeader, PagePreview, UnitSpinBox, page_thumbnail

ADD_TILE = -1  # item data for the "+ Add page" tile


def _key(text: str) -> QLabel:
    lab = QLabel(text); lab.setObjectName("Key"); return lab


def _clear(layout) -> None:
    """Empty a layout now. deleteLater alone leaves the widgets painting until the event loop runs."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()  # keep it: after setParent(None) the item no longer knows its widget
        if w:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout():
            _clear(item.layout())


def _when(iso: str) -> str:
    return iso.replace("T", " ")[:16]


# ---------------------------------------------------------------------------
class ProjectsView(QWidget):
    open_requested = Signal(str)      # folder
    settings_requested = Signal()
    go_pages = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Name", "Pages", "Page size", "Reading", "Folder", "Modified"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.open_requested.emit(self._folders[r]))
        lay.addWidget(self.table, 3)
        self.details = QWidget(); self.details.setObjectName("DetailsPane"); self.details.setAttribute(Qt.WA_StyledBackground, True)
        self.details_lay = QHBoxLayout(self.details); self.details_lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(self.details, 2)
        self._folders: list[str] = []
        self._projects: dict[str, Project | str] = {}
        self.open_folder: str | None = None

    def set_projects(self, folders: list[str], open_folder: str | None) -> None:
        self.open_folder = open_folder
        self._folders = list(folders)
        self.table.setRowCount(len(folders))
        for r, folder in enumerate(folders):
            try:
                p = load_project(folder)
                self._projects[folder] = p
                cells = [p.name + ("   (open)" if folder == open_folder else ""), str(len(p.pages)), p.paper,
                         "Right to left" if p.reading == "rtl" else "Left to right", folder, _when(p.modified)]
            except ValueError as e:
                self._projects[folder] = str(e)
                cells = [os.path.basename(folder), "", "", "", folder, "can't open: " + str(e)]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 0:
                    item.setIcon(icons.icon("projects"))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        if folders:
            row = folders.index(open_folder) if open_folder in folders else 0
            self.table.selectRow(row)
        else:
            self._show_details()

    def _clear_details(self) -> None:
        _clear(self.details_lay)

    def _show_details(self) -> None:
        self._clear_details()
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            face = QLabel(); face.setPixmap(icons.mascot(56))
            msg = QLabel("No projects yet. Use <b>New project…</b> to start a comic, or <b>Open…</b> a project folder.")
            msg.setWordWrap(True)
            self.details_lay.addWidget(face); self.details_lay.addWidget(msg, 1)
            return
        folder = self._folders[rows[0].row()]
        p = self._projects.get(folder)
        if not isinstance(p, Project):
            self.details_lay.addWidget(QLabel(f"This folder can't be opened: {p}"), 1)
            return
        left = QWidget(); f = QFormLayout(left); f.setContentsMargins(0, 0, 0, 0)
        title = QLabel(p.name); title.setObjectName("GroupTitle"); f.addRow(title)
        done = sum(e.status == "done" for e in p.pages)
        s = p.size
        for k, v in [("Chapter", p.chapter), ("Pages", f"{len(p.pages)} ({done} done)"),
                     ("Page size", f"{p.paper} · {s.trim_w:g} × {s.trim_h:g} mm, {s.bleed:g} mm bleed"),
                     ("Resolution", f"{s.dpi} dpi, drawn at {p.work_scale}×"),
                     ("Reading order", "Right to left (manga)" if p.reading == "rtl" else "Left to right")]:
            f.addRow(_key(k), QLabel(v))
        btns = QHBoxLayout()
        if folder == self.open_folder:
            go = QPushButton("Go to pages"); go.setDefault(True); go.clicked.connect(self.go_pages.emit)
            st = QPushButton(icons.icon("gear"), "Project settings…"); st.clicked.connect(self.settings_requested.emit)
            btns.addWidget(go); btns.addWidget(st)
        else:
            op = QPushButton("Open project"); op.setDefault(True); op.clicked.connect(lambda: self.open_requested.emit(folder))
            btns.addWidget(op)
        btns.addStretch()
        f.addRow(btns)
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0)
        h = QLabel("Folder"); h.setObjectName("GroupTitle"); rl.addWidget(h)
        rl.addWidget(QLabel(folder))
        rl.addWidget(QLabel("    project.json"))
        for sub in p.folders:
            extra = f"  ({len(p.pages)} pages)" if sub == "pages" else ""
            rl.addWidget(QLabel(f"    {sub}/{extra}"))
        rl.addStretch()
        self.details_lay.addWidget(left, 1); self.details_lay.addWidget(right, 1)

    def selected_folder(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        return self._folders[rows[0].row()] if rows else None


# ---------------------------------------------------------------------------
class PagesView(QWidget):
    """Pages grouped by status, Windows 7 Explorer style, with a details pane."""

    selection_changed = Signal(int)
    open_requested = Signal(int)
    add_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.selected: int | None = None
        self.filter = ""
        self._thumbs: dict[int, tuple[str, QIcon]] = {}  # page -> (modified, icon), so lists redraw fast
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        lay.addWidget(self.scroll, 1)
        self.details = QWidget(); self.details.setObjectName("DetailsPane"); self.details.setAttribute(Qt.WA_StyledBackground, True)
        self.details_lay = QHBoxLayout(self.details); self.details_lay.setContentsMargins(16, 8, 16, 8); self.details_lay.setSpacing(18)
        lay.addWidget(self.details)
        self.lists: dict[str, QListWidget] = {}

    def set_project(self, project: Project | None, selected: int | None = None) -> None:
        self.project = project
        self.selected = selected
        self.refresh()

    def _icon(self, number: int) -> QIcon:
        e = self.project.entry(number)
        cached = self._thumbs.get(number)
        if cached and cached[0] == e.modified:
            return cached[1]
        try:
            ic = QIcon(page_thumbnail(self.project.load_page(number), 56, os.path.dirname(self.project.page_path(number))))
        except (ValueError, OSError):
            ic = icons.icon("alert", theme.DANGER, 48)
        self._thumbs[number] = (e.modified, ic)
        return ic

    def refresh(self) -> None:
        body = QWidget(); grid = QVBoxLayout(body); grid.setContentsMargins(16, 6, 16, 16); grid.setSpacing(0)
        self.lists = {}
        if not self.project:
            face = QLabel(); face.setPixmap(icons.mascot(96)); face.setAlignment(Qt.AlignCenter)
            msg = QLabel("No project open. Go to <b>All projects</b> to make one or open one."); msg.setAlignment(Qt.AlignCenter)
            grid.addStretch(); grid.addWidget(face); grid.addWidget(msg); grid.addStretch()
            self.scroll.setWidget(body)
            self._details()
            return
        q = self.filter.strip().lower()
        for status in STATUSES:
            entries = [e for e in self.project.pages if e.status == status and
                       (not q or q in f"page_{e.number:02d}" or q in status)]
            grid.addWidget(GroupHeader(f"{theme.STATUS_LABELS[status]} ({len(entries)})"))
            lw = QListWidget()
            lw.setViewMode(QListView.IconMode); lw.setIconSize(QSize(56, 88)); lw.setGridSize(QSize(112, 128))
            lw.setResizeMode(QListView.Adjust); lw.setMovement(QListView.Static); lw.setWrapping(True)
            lw.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); lw.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            lw.setFrameShape(QFrame.NoFrame)
            for e in entries:
                item = QListWidgetItem(self._icon(e.number), f"page_{e.number:02d}")
                item.setData(Qt.UserRole, e.number)
                item.setToolTip(f"page_{e.number:02d} · {theme.STATUS_LABELS[e.status]} · modified {_when(e.modified)}")
                lw.addItem(item)
                if e.number == self.selected:
                    item.setSelected(True)
            if status == "thumbs":
                add = QListWidgetItem(icons.icon("plus", theme.ACCENT_TEXT, 40), "Add page")
                add.setData(Qt.UserRole, ADD_TILE)
                add.setForeground(QColor(theme.ACCENT_TEXT))
                add.setToolTip("Add a page, or batch generate several")
                lw.addItem(add)
            if lw.count() == 0:
                empty = QLabel("Nothing to letter yet. Pages land here after Colors." if status == "letters" else "No pages here.")
                empty.setObjectName("Hint"); grid.addWidget(empty)
                continue
            per_row = max(1, (self.scroll.viewport().width() - 40) // 112)
            rows = (lw.count() + per_row - 1) // per_row
            lw.setFixedHeight(rows * 128 + 6)
            lw.itemClicked.connect(self._clicked)
            lw.itemDoubleClicked.connect(self._double_clicked)
            self.lists[status] = lw
            grid.addWidget(lw)
        grid.addStretch()
        self.scroll.setWidget(body)
        self._details()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.project:
            self.refresh()

    def _clicked(self, item: QListWidgetItem) -> None:
        n = item.data(Qt.UserRole)
        if n == ADD_TILE:
            item.setSelected(False)
            self.add_requested.emit()
            return
        for lw in self.lists.values():
            if lw is not item.listWidget():
                lw.clearSelection()
        self.selected = n
        self._details()
        self.selection_changed.emit(n)

    def _double_clicked(self, item: QListWidgetItem) -> None:
        n = item.data(Qt.UserRole)
        if n != ADD_TILE:
            self.open_requested.emit(n)

    def _details(self) -> None:
        _clear(self.details_lay)
        if not self.project or self.selected is None:
            self.details.setVisible(False)
            return
        try:
            e = self.project.entry(self.selected)
            page = self.project.load_page(self.selected)
        except (KeyError, ValueError, OSError):
            self.details.setVisible(False)
            return
        self.details.setVisible(True)
        thumb = QLabel(); thumb.setPixmap(page_thumbnail(page, 34, os.path.dirname(self.project.page_path(page.number))))
        thumb.setStyleSheet(f"background: {theme.CANVAS}; padding: 3px 7px;")
        self.details_lay.addWidget(thumb)
        col = QVBoxLayout(); name = QLabel(f"<b>page_{e.number:02d}.svg</b>"); col.addWidget(name)
        kind = f"Drawn page · {page.art.href}" if page.is_art else "Comic page"
        col.addWidget(_key(f"{kind} · {theme.STATUS_LABELS[e.status]}"))
        self.details_lay.addLayout(col)
        st = QVBoxLayout(); st.addWidget(_key("Status"))
        combo = QComboBox()
        for s in STATUSES:
            combo.addItem(theme.STATUS_LABELS[s], s)
        combo.setCurrentIndex(STATUSES.index(e.status))
        combo.currentIndexChanged.connect(lambda i, n=e.number: self._set_status(n, STATUSES[i]))
        st.addWidget(combo); self.details_lay.addLayout(st)
        s = page.size
        recipe = page.layout
        how = {"bsp": f"random, seed {recipe.get('seed')}", "preset": f"preset {recipe.get('name')}",
               "grid": "grid", "art": f"drawn, {page.art.px_w} × {page.art.px_h} px" if page.art else "drawn"}.get(
            recipe.get("kind"), "custom")
        balloons = len(page.balloons or ())
        for k, v in [("Panels" if not page.is_art else "Balloons", str(len(page.cells) if not page.is_art else balloons)),
                     ("Layout", how),
                     # Drawn pages get their size from pixels, so it's rarely a round number: one decimal is plenty.
                     ("Size", f"{s.trim_w:.1f} × {s.trim_h:.1f} mm, {s.bleed:g} mm bleed".replace(".0 ", " ").replace(".0 mm", " mm")), ("Modified", _when(e.modified))]:
            c = QVBoxLayout(); c.addWidget(_key(k)); c.addWidget(QLabel(v)); self.details_lay.addLayout(c)
        self.details_lay.addStretch()

    def _set_status(self, number: int, status: str) -> None:
        self.project.set_status(number, status)
        self.window().toast(f"Moved to {theme.STATUS_LABELS[status]}", f"page_{number:02d} is now in {theme.STATUS_LABELS[status]}.")
        self.refresh()


# ---------------------------------------------------------------------------
class BuilderView(QWidget):
    """
    Edit one page: size, units, panel style, gutter, layout. The preview
    updates live; nothing is written until Save page.
    """

    dirty_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.saved: Page | None = None
        self.draft: Page | None = None
        self._loading = False
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        side = QScrollArea(); side.setWidgetResizable(True); side.setFrameShape(QFrame.NoFrame); side.setFixedWidth(300)
        props = QWidget(); pl = QVBoxLayout(props); pl.setContentsMargins(12, 8, 12, 12)
        side.setWidget(props)
        lay.addWidget(side)
        # The canvas with the hand tools (prototype: layout_canvas.py).
        stage = QWidget(); sl = QVBoxLayout(stage); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(0)
        tools = QWidget(); tools.setObjectName("DetailsPane"); tools.setAttribute(Qt.WA_StyledBackground, True)
        tl = QHBoxLayout(tools); tl.setContentsMargins(10, 4, 10, 4); tl.setSpacing(4)
        self.tool_buttons = {}
        group = QButtonGroup(self)
        for key, label, tip in (("select", "Select", "Drag a gutter to slide it; click an inset to move or resize it. Delete removes."),
                                ("knife", "Knife", "Drag across a panel to cut it. Shift: through the middle; Ctrl: 15° steps; Alt: free."),
                                ("inset", "Inset panel", "Drag a rectangle: a panel on top of the others."),
                                ("merge", "Merge", "Click a gutter to join the panels on both sides, or an inset to remove it.")):
            b = QPushButton(label); b.setCheckable(True); b.setToolTip(tip); b.setProperty("tool", key)
            group.addButton(b); tl.addWidget(b); self.tool_buttons[key] = b
        group.buttonClicked.connect(lambda b: self.set_tool(b.property("tool")))
        tl.addSpacing(12)
        self.blank_btn = QPushButton("Blank page"); self.blank_btn.setToolTip("Start over from one panel")
        self.undo_btn = QPushButton("Undo"); self.redo_btn = QPushButton("Redo")
        for b in (self.blank_btn, self.undo_btn, self.redo_btn):
            tl.addWidget(b)
        tl.addSpacing(12)
        self.gap_box = QCheckBox("Gap around insets")
        self.gap_box.setToolTip("A white gap one gutter wide around inset panels, so the lines behind them stop short.")
        self.gap_box.setChecked(True)
        self.gap_box.toggled.connect(self._gap_toggled)
        tl.addWidget(self.gap_box)
        tl.addStretch()
        sl.addWidget(tools)
        self.tool_hint = QLabel(); self.tool_hint.setObjectName("Hint"); self.tool_hint.setContentsMargins(12, 4, 12, 2)
        sl.addWidget(self.tool_hint)
        self.preview = LayoutCanvas()
        sl.addWidget(self.preview, 1)
        lay.addWidget(stage, 1)
        self.preview.layout_edited.connect(self._layout_edited)
        self.preview.layout_preview.connect(self._layout_preview)
        self._drag_base: Page | None = None
        self.preview.message.connect(self.tool_hint.setText)
        self.blank_btn.clicked.connect(self.blank_layout)
        self.undo_btn.clicked.connect(self.undo); self.redo_btn.clicked.connect(self.redo)
        QShortcut(QKeySequence.Undo, self, self.undo)
        QShortcut(QKeySequence.Redo, self, self.redo)
        self.undo_stack: list[Page] = []
        self.redo_stack: list[Page] = []
        self.set_tool("select")

        size = QGroupBox("Page size"); sf = QFormLayout(size)
        self.paper = QComboBox()
        for n in PAPER_SIZES:
            self.paper.addItem(n)
        self.paper.addItem("Custom")
        self.trim_w = UnitSpinBox(168, 20, 1000); self.trim_h = UnitSpinBox(260, 20, 1000)
        self.bleed = UnitSpinBox(3, 0, 50); self.safe = UnitSpinBox(5, 0, 50); self.margin = UnitSpinBox(8, 0, 80)
        self.dpi = QSpinBox(); self.dpi.setRange(72, 2400); self.dpi.setSuffix(" dpi")
        sf.addRow("Preset:", self.paper); sf.addRow("Trim width:", self.trim_w); sf.addRow("Trim height:", self.trim_h)
        sf.addRow("Bleed:", self.bleed); sf.addRow("Safe area:", self.safe); sf.addRow("Margin:", self.margin)
        sf.addRow("Resolution:", self.dpi)
        self.canvas_info = QLabel(); self.canvas_info.setObjectName("Hint"); self.canvas_info.setWordWrap(True)
        sf.addRow(self.canvas_info)
        self.safe_warning = QLabel(); self.safe_warning.setObjectName("Verdict"); self.safe_warning.setProperty("kind", "bad")
        self.safe_warning.setWordWrap(True)
        sf.addRow(self.safe_warning)
        pl.addWidget(size)

        units = QGroupBox("Units"); ul = QHBoxLayout(units)
        self.unit_group = QButtonGroup(self)
        for u in ("mm", "cm", "in"):
            b = QRadioButton(u); b.setProperty("unit", u); b.setChecked(u == "mm"); self.unit_group.addButton(b); ul.addWidget(b)
        ul.addStretch()
        pl.addWidget(units)

        style = QGroupBox("Panels"); stf = QFormLayout(style)
        self.stroke = QPushButton(); self.stroke.setFixedWidth(90); self.stroke.clicked.connect(self._pick_stroke)
        self.stroke_w = UnitSpinBox(0.6, 0.05, 5)
        self.fill = QComboBox()
        for label, value in (("None", None), ("White", "#ffffff"), ("Pale pink", "#fff1f6")):
            self.fill.addItem(label, value)
        self.radius = UnitSpinBox(0, 0, 20)
        self.gutter = UnitSpinBox(3, 0, 30)
        stf.addRow("Stroke colour:", self.stroke); stf.addRow("Stroke width:", self.stroke_w); stf.addRow("Fill:", self.fill)
        stf.addRow("Corner radius:", self.radius); stf.addRow("Gutter:", self.gutter)
        self.layout_info = QLabel(); self.layout_info.setObjectName("Hint"); self.layout_info.setWordWrap(True)
        stf.addRow(self.layout_info)
        pl.addWidget(style)
        pl.addStretch()

        self.paper.currentTextChanged.connect(self._paper_changed)
        for w in (self.trim_w, self.trim_h):
            w.mmChanged.connect(lambda _: self._set_custom())
        for w in (self.trim_w, self.trim_h, self.bleed, self.safe, self.margin, self.stroke_w, self.radius, self.gutter):
            w.mmChanged.connect(lambda _: self._changed())
        self.dpi.valueChanged.connect(lambda _: self._changed())
        self.fill.currentIndexChanged.connect(lambda _: self._changed())
        self.unit_group.buttonClicked.connect(self._unit_changed)
        self._stroke_color = "#1b1b1b"

    # ---------- loading ----------
    def load(self, project: Project, number: int) -> None:
        self.project = project
        self.saved = self.draft = project.load_page(number)
        self.undo_stack, self.redo_stack = [], []
        self._loading = True
        p, s = self.draft, self.draft.size
        named = next((n for n, (w, h) in PAPER_SIZES.items() if (w, h) == (s.trim_w, s.trim_h)), "Custom")
        self.paper.setCurrentText(named)
        for w, v in ((self.trim_w, s.trim_w), (self.trim_h, s.trim_h), (self.bleed, s.bleed), (self.safe, s.safe),
                     (self.margin, s.margin), (self.stroke_w, p.style.stroke_width), (self.radius, p.style.corner_radius),
                     (self.gutter, p.gutter)):
            w.set_mm(v)
        self.dpi.setValue(s.dpi)
        self._stroke_color = p.style.stroke
        self.fill.setCurrentIndex(max(0, self.fill.findData(p.style.fill)))
        self._loading = False
        self._show()

    @property
    def dirty(self) -> bool:
        return self.draft is not None and self.draft != self.saved

    # ---------- hand tools (prototype) ----------
    TOOL_HINTS = {
        "select": "Select: drag a gutter to slide it. Click an inset to move it or resize it by its handles. Delete removes.",
        "knife": "Knife: drag across a panel to cut it. Shift: through the middle · Ctrl: 15° steps · Alt: no snapping. Drag a gutter to slide it.",
        "inset": "Inset panel: drag a rectangle to put a panel on top of the others.",
        "merge": "Merge: click a gutter to join the panels on both sides, or click an inset to remove it.",
    }

    def set_tool(self, tool: str) -> None:
        self.preview.tool = tool
        self.tool_buttons[tool].setChecked(True)
        self.tool_hint.setText(self.TOOL_HINTS[tool])
        self.preview.update()

    def _page_for(self, layout: dict) -> Page:
        d = self.draft
        new = page_manual(d.number, d.size, layout, gutter=d.gutter, reading=d.reading, style=d.style)
        new = replace(new, balloons=d.balloons, art=d.art)
        new.panels()  # refuses a layout whose panels the gutter would swallow
        return new

    def _layout_preview(self, layout: dict) -> None:
        """A drag in progress: show it, but only the finished drag becomes an undo step."""
        try:
            new = self._page_for(layout)
        except ValueError:
            return
        if self._drag_base is None:
            self._drag_base = self.draft
        self.set_draft(new)

    def _gap_toggled(self, on: bool) -> None:
        if self.draft and self.draft.layout.get("kind") == "manual" and self.draft.layout.get("inset_gap", True) != on:
            self._layout_edited(dict(self.draft.layout, inset_gap=on))

    def _layout_edited(self, layout: dict) -> None:
        base, self._drag_base = self._drag_base, None
        try:
            new = self._page_for(layout)
        except ValueError as e:
            self.tool_hint.setText(f"No change: {e}.")
            if base is not None:
                self.set_draft(base)
            return
        d = base or self.draft
        self.undo_stack.append(d)
        self.redo_stack.clear()
        self.set_draft(new)
        self.dirty_changed.emit(self.dirty)  # also refreshes the status bar's panel count
        self.tool_hint.setText(self.TOOL_HINTS[self.preview.tool])

    def blank_layout(self) -> None:
        if self.draft:
            from cpb_core.layouts.knife import empty
            self._layout_edited(empty())

    def undo(self) -> None:
        if self.undo_stack:
            self.redo_stack.append(self.draft)
            self.set_draft(self.undo_stack.pop())
            self.dirty_changed.emit(self.dirty)

    def redo(self) -> None:
        if self.redo_stack:
            self.undo_stack.append(self.draft)
            self.set_draft(self.redo_stack.pop())
            self.dirty_changed.emit(self.dirty)

    # ---------- editing ----------
    def _paper_changed(self, name: str) -> None:
        if name in PAPER_SIZES and not self._loading:
            self._loading = True
            w, h = PAPER_SIZES[name]
            self.trim_w.set_mm(w); self.trim_h.set_mm(h)
            self._loading = False
            self._changed()

    def _set_custom(self) -> None:
        if not self._loading and self.paper.currentText() != "Custom":
            self.paper.blockSignals(True); self.paper.setCurrentText("Custom"); self.paper.blockSignals(False)

    def _unit_changed(self, button) -> None:
        u = button.property("unit")
        for w in (self.trim_w, self.trim_h, self.bleed, self.safe, self.margin, self.stroke_w, self.radius, self.gutter):
            w.set_unit(u)
        self.window().toast("Units changed", f"Showing {u}. The page itself didn't change.")
        self._show()

    def _pick_stroke(self) -> None:
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self._stroke_color), self, "Panel stroke colour")
        if c.isValid():
            self._stroke_color = c.name()
            self._changed()

    def _changed(self) -> None:
        if self._loading or not self.draft:
            return
        try:
            size = PageSize(trim_w=self.trim_w.mm(), trim_h=self.trim_h.mm(), bleed=self.bleed.mm(), safe=self.safe.mm(),
                            margin=self.margin.mm(), dpi=self.dpi.value())
            style = PanelStyle(stroke=self._stroke_color, stroke_width=self.stroke_w.mm(), fill=self.fill.currentData(),
                               corner_radius=self.radius.mm())
            base = replace(self.draft, gutter=self.gutter.mm(), style=style)
            new = rebuild(base, size) if size != self.draft.size else base
            new.panels()  # raises if the gutter no longer fits
        except ValueError as e:
            self.canvas_info.setText(f"Can't use that: {e}.")
            return
        self.set_draft(new)

    def set_draft(self, page: Page) -> None:
        was = self.dirty
        self.draft = page
        self._show()
        if self.dirty != was:
            self.dirty_changed.emit(self.dirty)

    def _show(self) -> None:
        if not self.draft:
            return
        p, s = self.draft, self.draft.size
        unit = self.unit_group.checkedButton().property("unit")
        from cpb_core.units import from_mm
        w, h = s.canvas_px()
        self.canvas_info.setText(f"Canvas: {from_mm(s.canvas_w, unit):g} × {from_mm(s.canvas_h, unit):g} {unit} "
                                 f"(trim + 2 × bleed) · {w} × {h} px")
        inside = p.geometry().panels_inside_safe_area()
        self.safe_warning.setText("The panel margin is smaller than the safe area, so panel edges may be trimmed in print.")
        self.safe_warning.setVisible(not inside)
        self.stroke.setText(self._stroke_color)
        self.stroke.setStyleSheet(f"QPushButton {{ border-left: 14px solid {self._stroke_color}; }}")
        r = p.layout
        how = {"bsp": f"Random layout, seed {r.get('seed')} ({r.get('mode')})", "preset": f"Preset {r.get('name')}",
               "grid": "Grid", "manual": "Hand-cut layout"}.get(r.get("kind"), "Custom cells")
        self.undo_btn.setEnabled(bool(self.undo_stack)); self.redo_btn.setEnabled(bool(self.redo_stack))
        self.gap_box.blockSignals(True)
        self.gap_box.setChecked(r.get("inset_gap", True))
        self.gap_box.setEnabled(r.get("kind") == "manual" and bool(r.get("insets")))
        self.gap_box.blockSignals(False)
        asked = r.get("panels")
        note = f" Asked for {asked}; only {len(p.cells)} fit." if asked and asked > len(p.cells) else ""
        self.layout_info.setText(f"{how} · {len(p.cells)} panels · {'right to left' if p.reading == 'rtl' else 'left to right'}.{note}")
        self.preview.set_page(p)


# ---------------------------------------------------------------------------
class PlaceholderView(QWidget):
    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch()
        face = QLabel(); face.setPixmap(icons.mascot(110)); face.setAlignment(Qt.AlignCenter)
        t = QLabel(title); t.setObjectName("BigTitle"); t.setAlignment(Qt.AlignCenter)
        m = QLabel(text); m.setObjectName("Hint"); m.setAlignment(Qt.AlignCenter); m.setWordWrap(True)
        for w in (face, t, m):
            lay.addWidget(w)
        lay.addStretch()
