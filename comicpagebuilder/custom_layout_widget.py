"""
custom_layout_widget.py 

Tab 2: Custom Layout
Includes both the BSP randomizer and an Interactive Boolean Grid Builder.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QPushButton, QLabel, QSpinBox,
    QDoubleSpinBox, QComboBox, QFrame, QInputDialog,
    QMessageBox, QTabWidget, QGraphicsView, QGraphicsScene, QGraphicsRectItem
)
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtSvg import QSvgWidget

from .layout_browser_widget import rects_to_svg
from .layout_generator import DEFAULT_GUTTER_MM

_USER_LAYOUTS_DIR = os.path.join(
    os.path.dirname(__file__), "resources", "layouts", "user"
)
PREVIEW_W = 120
PREVIEW_H = 160

# ---------------------------------------------------------------------------
# Interactive Grid Builder Classes
# ---------------------------------------------------------------------------
class ClickableGutter(QGraphicsRectItem):
    def __init__(self, r, c, is_horizontal, builder):
        super().__init__()
        self.r = r
        self.c = c
        self.is_horizontal = is_horizontal
        self.builder = builder
        self.active = True  # True = cut (panels separate), False = merged
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptHoverEvents(True)
        self._update_color()

    def _update_color(self, hover=False):
        if hover:
            self.setBrush(QBrush(QColor("#5599ff")))
        else:
            if self.active:
                self.setBrush(QBrush(QColor("#2b2b2b"))) # Matches background (cut)
            else:
                self.setBrush(QBrush(QColor("#3c3c3c"))) # Matches panel (merged)
        self.setPen(QPen(Qt.NoPen))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active = not self.active
            self.builder.update_preview()

    def hoverEnterEvent(self, event):
        self._update_color(hover=True)

    def hoverLeaveEvent(self, event):
        self._update_color(hover=False)

class InteractiveGridBuilder(QWidget):
    layout_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = 3
        self.cols = 2
        self.v_gutters = []
        self.h_gutters = []
        self.intersections = {}

        self._build_ui()
        self._rebuild_grid()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        
        hint = QLabel(
            "Click the dividing lines to merge or split adjacent panels.\n"
            "Note: Non-rectangular merges (like L-shapes) will generate overlapping bounding boxes."
        )
        hint.setStyleSheet("color:#888; font-size:10px;")
        root.addWidget(hint)

        controls = QHBoxLayout()
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 10)
        self.spin_rows.setValue(self.rows)
        self.spin_rows.valueChanged.connect(self._on_grid_size_changed)

        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 10)
        self.spin_cols.setValue(self.cols)
        self.spin_cols.valueChanged.connect(self._on_grid_size_changed)

        controls.addWidget(QLabel("Grid Rows:"))
        controls.addWidget(self.spin_rows)
        controls.addWidget(QLabel("Cols:"))
        controls.addWidget(self.spin_cols)
        controls.addStretch()
        root.addLayout(controls)

        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setStyleSheet("background: #2b2b2b; border: 1px solid #444;")
        self.view.setMinimumHeight(250)
        root.addWidget(self.view)

    def _on_grid_size_changed(self):
        self.rows = self.spin_rows.value()
        self.cols = self.spin_cols.value()
        self._rebuild_grid()

    def _rebuild_grid(self):
        self.scene.clear()
        self.v_gutters.clear()
        self.h_gutters.clear()
        self.intersections.clear()

        # Arbitrary visual sizes for the interactive scene
        cell_w, cell_h = 60, 80
        g_thick = 8

        # Draw Base Cells
        for r in range(self.rows):
            for c in range(self.cols):
                x = c * (cell_w + g_thick)
                y = r * (cell_h + g_thick)
                rect = QGraphicsRectItem(x, y, cell_w, cell_h)
                rect.setBrush(QBrush(QColor("#3c3c3c")))
                rect.setPen(QPen(Qt.NoPen))
                self.scene.addItem(rect)

        # Draw Vertical Gutters
        for r in range(self.rows):
            row_v = []
            for c in range(self.cols - 1):
                x = c * (cell_w + g_thick) + cell_w
                y = r * (cell_h + g_thick)
                g = ClickableGutter(r, c, False, self)
                g.setRect(x, y, g_thick, cell_h)
                self.scene.addItem(g)
                row_v.append(g)
            self.v_gutters.append(row_v)

        # Draw Horizontal Gutters
        for r in range(self.rows - 1):
            row_h = []
            for c in range(self.cols):
                x = c * (cell_w + g_thick)
                y = r * (cell_h + g_thick) + cell_h
                g = ClickableGutter(r, c, True, self)
                g.setRect(x, y, cell_w, g_thick)
                self.scene.addItem(g)
                row_h.append(g)
            self.h_gutters.append(row_h)

        # Draw Intersections
        for r in range(self.rows - 1):
            for c in range(self.cols - 1):
                x = c * (cell_w + g_thick) + cell_w
                y = r * (cell_h + g_thick) + cell_h
                cross = QGraphicsRectItem(x, y, g_thick, g_thick)
                cross.setPen(QPen(Qt.NoPen))
                self.scene.addItem(cross)
                self.intersections[(r, c)] = cross

        self.view.setSceneRect(self.scene.itemsBoundingRect())
        self.update_preview()

    def extract_groups(self):
        parent = {}
        for r in range(self.rows):
            for c in range(self.cols):
                parent[(r, c)] = (r, c)

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            rootX = find(x)
            rootY = find(y)
            if rootX != rootY:
                parent[rootY] = rootX

        # Merge cells logically based on inactive gutters
        for r in range(self.rows):
            for c in range(self.cols - 1):
                if not self.v_gutters[r][c].active:
                    union((r, c), (r, c+1))

        for r in range(self.rows - 1):
            for c in range(self.cols):
                if not self.h_gutters[r][c].active:
                    union((r, c), (r+1, c))

        groups = {}
        for r in range(self.rows):
            for c in range(self.cols):
                root = find((r, c))
                if root not in groups:
                    groups[root] = []
                groups[root].append((r, c))

        return groups, find

    def update_preview(self):
        # Visually update the boolean grid UI
        for row in self.v_gutters:
            for g in row: g._update_color()
        for row in self.h_gutters:
            for g in row: g._update_color()

        groups, find = self.extract_groups()

        # Update intersection crosses
        for r in range(self.rows - 1):
            for c in range(self.cols - 1):
                if find((r,c)) == find((r,c+1)) == find((r+1,c)) == find((r+1,c+1)):
                    self.intersections[(r,c)].setBrush(QBrush(QColor("#3c3c3c")))
                else:
                    self.intersections[(r,c)].setBrush(QBrush(QColor("#2b2b2b")))

        self.layout_updated.emit()

    def get_layout_rects(self, bw, bh, gutter_mm):
        groups, _ = self.extract_groups()
        norm_gx = gutter_mm / bw if bw > 0 else 0.014
        norm_gy = gutter_mm / bh if bh > 0 else 0.010

        panel_w = (1.0 - (self.cols - 1) * norm_gx) / self.cols
        panel_h = (1.0 - (self.rows - 1) * norm_gy) / self.rows

        rects = []
        for root, cells in groups.items():
            min_r = min(cell[0] for cell in cells)
            max_r = max(cell[0] for cell in cells)
            min_c = min(cell[1] for cell in cells)
            max_c = max(cell[1] for cell in cells)

            x = min_c * (panel_w + norm_gx)
            y = min_r * (panel_h + norm_gy)
            w = (max_c - min_c + 1) * panel_w + (max_c - min_c) * norm_gx
            h = (max_r - min_r + 1) * panel_h + (max_r - min_r) * norm_gy

            rects.append({
                "x": round(x, 6),
                "y": round(y, 6),
                "width": round(w, 6),
                "height": round(h, 6)
            })

        return rects

# ---------------------------------------------------------------------------
# Main Custom Layout Widget
# ---------------------------------------------------------------------------
class CustomLayoutWidget(QWidget):
    """
    BSP randomizer and Interactive Grid.
    layout_ready(dict)          emits when user clicks "Use This Layout"
    layouts_changed()           emits after saving a layout (browser should reload)
    """
    layout_ready    = pyqtSignal(dict)
    layouts_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page_spec      = None
        self._current_layout = None
        self._build_ui()

    def set_page_spec(self, spec):
        self._page_spec = spec

    def current_layout(self):   return self._current_layout
    def has_layout(self):       return self._current_layout is not None

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ---- Generator Tabs ----
        self._gen_tabs = QTabWidget()

        # Tab 1: BSP Randomizer
        bsp_tab = QWidget()
        bsp_form = QFormLayout(bsp_tab)
        bsp_form.setSpacing(8)

        self._panels_spin = QSpinBox()
        self._panels_spin.setRange(1, 8)
        self._panels_spin.setValue(4)
        self._panels_spin.setToolTip("Number of panels (1-8). More than 8 becomes unreadable.")
        bsp_form.addRow("Panel count:", self._panels_spin)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Auto - cut the longer axis (balanced)",    "auto")
        self._mode_combo.addItem("Horizontal strips only",                   "horizontal")
        self._mode_combo.addItem("Vertical columns only",                    "vertical")
        self._mode_combo.addItem("Pure random - chaotic / experimental",     "random")
        bsp_form.addRow("Cut mode:", self._mode_combo)

        hint = QLabel(
            "Auto cuts the longer axis first - most readable results.\n"
            "Horizontal/Vertical only = strips or columns, good for specific styles.\n"
            "Pure random is experimental - great for finding new compositions."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #777; font-size: 9px;")
        bsp_form.addRow(hint)

        roll_row = QHBoxLayout()
        self._roll_btn = QPushButton("🎲 Roll Layout")
        self._roll_btn.setMinimumHeight(32)
        self._roll_btn.setStyleSheet(
            "QPushButton { font-size:13px; background:#2a3a5a;"
            " border:1px solid #5599ff; border-radius:4px; }"
            "QPushButton:hover { background:#3a4a6a; }"
        )
        self._roll_btn.clicked.connect(self._on_roll)
        roll_row.addWidget(self._roll_btn)

        self._reroll_btn = QPushButton("\u21ba")
        self._reroll_btn.setFixedWidth(32)
        self._reroll_btn.setMinimumHeight(32)
        self._reroll_btn.setToolTip("Re-roll with same settings")
        self._reroll_btn.setStyleSheet(
            "QPushButton { font-size:16px; background:#2b2b2b;"
            " border:1px solid #555; border-radius:4px; }"
            "QPushButton:hover { background:#333; }"
        )
        self._reroll_btn.clicked.connect(self._on_roll)
        roll_row.addWidget(self._reroll_btn)
        bsp_form.addRow(roll_row)
        
        self._gen_tabs.addTab(bsp_tab, "BSP Randomizer")

        # Tab 2: Interactive Grid
        grid_tab = QWidget()
        grid_layout = QVBoxLayout(grid_tab)
        grid_layout.setContentsMargins(4, 4, 4, 4)
        self._interactive_builder = InteractiveGridBuilder()
        self._interactive_builder.layout_updated.connect(self._on_interactive_updated)
        grid_layout.addWidget(self._interactive_builder)
        
        self._gen_tabs.addTab(grid_tab, "Interactive Grid")
        self._gen_tabs.currentChanged.connect(self._on_tab_changed)

        root.addWidget(self._gen_tabs)

        # ---- Shared Settings ----
        shared_group = QGroupBox("Shared Settings")
        shared_form = QFormLayout(shared_group)
        self._gutter_spin = QDoubleSpinBox()
        self._gutter_spin.setRange(0.5, 20.0)
        self._gutter_spin.setValue(DEFAULT_GUTTER_MM)
        self._gutter_spin.setDecimals(1)
        self._gutter_spin.setSuffix(" mm")
        self._gutter_spin.setSingleStep(0.5)
        self._gutter_spin.setToolTip(
            "Space between panels.\n"
            "Separate from line strength (border thickness).\n"
            "3mm is standard for most comics."
        )
        self._gutter_spin.valueChanged.connect(self._on_shared_settings_changed)
        shared_form.addRow("Gutter (panel spacing):", self._gutter_spin)
        root.addWidget(shared_group)

        # ---- Live preview ----
        preview_group  = QGroupBox("Preview")
        preview_layout = QHBoxLayout(preview_group)

        self._preview_svg = QSvgWidget()
        self._preview_svg.setFixedSize(PREVIEW_W, PREVIEW_H)
        self._preview_svg.load(
            rects_to_svg([{"x":0,"y":0,"width":1,"height":1}], PREVIEW_W, PREVIEW_H)
        )
        preview_layout.addWidget(self._preview_svg)

        info_col = QVBoxLayout()
        self._preview_label = QLabel("Configure a layout to preview it here.")
        self._preview_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._preview_label.setStyleSheet("color:#888; font-size:10px;")
        self._preview_label.setWordWrap(True)
        info_col.addWidget(self._preview_label)
        info_col.addStretch()

        preview_layout.addLayout(info_col, stretch=1)
        root.addWidget(preview_group)

        # ---- Action buttons ----
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#444;")
        root.addWidget(sep)

        actions = QHBoxLayout()
        actions.setSpacing(6)

        self._use_btn = QPushButton("\u2713  Use This Layout")
        self._use_btn.setEnabled(False)
        self._use_btn.setMinimumHeight(30)
        self._use_btn.setToolTip("Send to the generate buttons at the bottom")
        self._use_btn.clicked.connect(self._on_use)
        actions.addWidget(self._use_btn)

        self._save_generated_btn = QPushButton("\U0001f4be  Save Layout\u2026")
        self._save_generated_btn.setEnabled(False)
        self._save_generated_btn.setMinimumHeight(30)
        self._save_generated_btn.setToolTip(
            "Save this generated layout as a JSON preset.\n"
            "It will appear in the Layout tab under ★ Saved."
        )
        self._save_generated_btn.clicked.connect(self._on_save_generated)
        actions.addWidget(self._save_generated_btn)

        root.addWidget(QWidget())  # spacer
        root.addLayout(actions)

        # ---- Save from open document ----
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#444;")
        root.addWidget(sep2)

        doc_group  = QGroupBox("Save Current Document as Layout Preset")
        doc_layout = QVBoxLayout(doc_group)
        doc_hint = QLabel(
            "If you've adjusted your panels in Krita (using the panel tool, "
            "moving shapes, etc.), you can save the current state of the Panels "
            "layer as a reusable preset."
        )
        doc_hint.setWordWrap(True)
        doc_hint.setStyleSheet("color:#777; font-size:9px;")
        doc_layout.addWidget(doc_hint)

        self._save_doc_btn = QPushButton("\U0001f4c4  Save Open Document as Preset\u2026")
        self._save_doc_btn.setMinimumHeight(28)
        self._save_doc_btn.clicked.connect(self._on_save_from_document)
        doc_layout.addWidget(self._save_doc_btn)

        root.addWidget(doc_group)
        root.addStretch()

    # -----------------------------------------------------------------------
    # Handlers
    # -----------------------------------------------------------------------
    def _on_tab_changed(self, index):
        if index == 0:
            self._on_roll()
        else:
            self._on_interactive_updated()

    def _on_shared_settings_changed(self):
        self._on_tab_changed(self._gen_tabs.currentIndex())

    def _on_interactive_updated(self):
        from .layout_generator import make_layout_dict
        gutter = self._gutter_spin.value()
        
        if self._page_spec:
            bw = self._page_spec.effective_binding_w()
            bh = self._page_spec.effective_binding_h()
        else:
            bw, bh = 210.0, 297.0
            
        rects = self._interactive_builder.get_layout_rects(bw, bh, gutter)
        n = len(rects)
        layout = make_layout_dict(rects, label=f"Interactive {n}P")
        
        self._current_layout = layout
        self._preview_svg.load(rects_to_svg(rects, PREVIEW_W, PREVIEW_H))
        
        self._preview_label.setText(
            f"{n} panel{'s' if n != 1 else ''}\n"
            f"Mode: Interactive Grid\n"
            f"Gutter: {gutter}mm\n\n"
            "Happy with it?\n"
            "  Use or Save below."
        )
        self._use_btn.setEnabled(True)
        self._save_generated_btn.setEnabled(True)

    def _on_roll(self):
        from .layout_generator import generate_layout, make_layout_dict

        n      = self._panels_spin.value()
        mode   = self._mode_combo.currentData()
        gutter = self._gutter_spin.value()

        if self._page_spec:
            bw = self._page_spec.effective_binding_w()
            bh = self._page_spec.effective_binding_h()
        else:
            bw, bh = 210.0, 297.0

        rects  = generate_layout(n, bw, bh, gutter_mm=gutter, cut_mode=mode)
        got    = len(rects)   # can be < n when panels hit the minimum size
        layout = make_layout_dict(rects, label=f"Random {got}P ({mode})")

        self._current_layout = layout
        self._preview_svg.load(rects_to_svg(rects, PREVIEW_W, PREVIEW_H))

        count_line = f"{got} panel{'s' if got != 1 else ''}"
        if got < n:
            count_line += f" (asked for {n}; no room for more at this page size)"
        self._preview_label.setText(
            f"{count_line}\n"
            f"Mode: {mode}\n"
            f"Gutter: {gutter}mm\n\n"
            "Happy with it?\n"
            "  Use or Save below.\n"
            "  Roll again for a new one."
        )
        self._use_btn.setEnabled(True)
        self._save_generated_btn.setEnabled(True)

    def _on_use(self):
        if self._current_layout:
            self.layout_ready.emit(self._current_layout)

    def _on_save_generated(self):
        if not self._current_layout:
            return
        self._save_rects(self._current_layout["rects"])

    def _on_save_from_document(self):
        try:
            from krita import Krita
            from .document_builder import extract_layout_from_document

            app = Krita.instance()
            win = app.activeWindow()

            if not win or not win.activeView():
                QMessageBox.warning(self, "No Document", "No active document open.")
                return

            doc = win.activeView().document()
            rects = extract_layout_from_document(doc)

            if not rects:
                QMessageBox.warning(self, "No Panels Found",
                    "Could not find a 'Panels' layer with shapes in this document.")
                return

            self._save_rects(rects)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _save_rects(self, rects: list):
        from .layout_generator import save_layout_json

        name, ok = QInputDialog.getText(
            self, "Save Layout Preset",
            "Name for this layout (will appear in ★ Saved tab):"
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        try:
            path = save_layout_json(rects, name, _USER_LAYOUTS_DIR)
            QMessageBox.information(
                self, "Saved",
                f'"{name}" saved.\nIt will appear in the Layout tab -> Saved.'
            )
            self.layouts_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))