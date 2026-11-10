"""
layout_browser_widget.py — Tab 1: Layout Browser

Preset + user-saved layouts. Saved tab shows only user layouts.
"""

import json
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QGridLayout, QPushButton, QLabel, QFrame, QButtonGroup,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtSvg import QSvgWidget


_LAYOUTS_DIR      = os.path.join(os.path.dirname(__file__), "resources", "layouts")
_USER_LAYOUTS_DIR = os.path.join(_LAYOUTS_DIR, "user")

THUMB_W = 90
THUMB_H = 120


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def load_all_layouts(include_user: bool = True) -> list:
    layouts = []

    def _load_dir(dirpath: str, is_user: bool):
        if not os.path.isdir(dirpath):
            return
        for fname in sorted(os.listdir(dirpath)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(dirpath, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            rects = [
                item["data"]
                for item in data.get("layout", [])
                if item.get("type") == "rect"
            ]
            if not rects:
                continue
            name     = os.path.splitext(fname)[0]
            is_title = name.lower().startswith("title")
            # Count the rects, don't trust the filename: several bundled
            # "4 frames ..." presets actually contain 5 panels.
            frames   = len(rects)
            layouts.append({
                "path":     path,
                "name":     name,
                "frames":   frames,
                "is_title": is_title,
                "is_user":  is_user,
                "rects":    rects,
            })

    _load_dir(_LAYOUTS_DIR, is_user=False)
    if include_user:
        _load_dir(_USER_LAYOUTS_DIR, is_user=True)

    return layouts


def rects_to_svg(rects: list, w: int, h: int, line_px: float = 1.5) -> bytes:
    padding = 4
    draw_w  = w - padding * 2
    draw_h  = h - padding * 2
    parts   = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
        f'<rect width="{w}" height="{h}" fill="#2b2b2b"/>'
    ]
    for r in rects:
        rx = padding + r["x"]     * draw_w
        ry = padding + r["y"]     * draw_h
        rw = r["width"]  * draw_w
        rh = r["height"] * draw_h
        parts.append(
            f'<rect x="{rx:.2f}" y="{ry:.2f}" '
            f'width="{rw:.2f}" height="{rh:.2f}" '
            f'fill="#3c3c3c" stroke="#cccccc" stroke-width="{line_px}"/>'
        )
    parts.append("</svg>")
    return "".join(parts).encode("utf-8")


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------

class LayoutThumb(QFrame):
    clicked        = pyqtSignal(dict)
    double_clicked = pyqtSignal(dict)

    def __init__(self, layout: dict, parent=None):
        super().__init__(parent)
        self._layout = layout
        self.setFixedSize(THUMB_W + 8, THUMB_H + 28)
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        self.set_selected(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        self._svg = QSvgWidget()
        self._svg.setFixedSize(THUMB_W, THUMB_H)
        self._svg.load(rects_to_svg(layout["rects"], THUMB_W, THUMB_H))
        root.addWidget(self._svg, alignment=Qt.AlignCenter)

        tag = "\u2605 " if layout.get("is_user") else ""
        lbl_text = "Title" if layout["is_title"] else f"{layout['frames']}P"
        lbl = QLabel(f"{tag}{lbl_text}")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 9px; color: #aaa;")
        root.addWidget(lbl)

    def set_selected(self, yes: bool):
        if yes:
            self.setStyleSheet(
                "QFrame { border: 2px solid #5599ff; border-radius: 4px; background: #1e2a3a; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { border: 1px solid #444; border-radius: 4px; background: #232323; }"
                "QFrame:hover { border-color: #777; background: #2a2a2a; }"
            )

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self._layout)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.double_clicked.emit(self._layout)


# ---------------------------------------------------------------------------
# Browser widget
# ---------------------------------------------------------------------------

class LayoutBrowserWidget(QWidget):
    layout_selected  = pyqtSignal(dict)
    layout_confirmed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_layouts     = load_all_layouts()
        self._current_filter  = "All"
        self._selected_thumb  = None
        self._selected_layout = None
        self._thumbs          = []
        self._build_ui()
        self._populate_grid("All")

    def selected_layout(self):  return self._selected_layout
    def has_selection(self):    return self._selected_layout is not None

    def reload_layouts(self):
        """Reload layouts from disk (call after saving a new user layout)."""
        self._all_layouts = load_all_layouts()
        self._populate_grid(self._current_filter)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Filter tabs
        tab_bar = QHBoxLayout()
        tab_bar.setSpacing(2)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)

        _TAB_STYLE = (
            "QPushButton { border:1px solid #555; border-radius:3px;"
            " padding:0 8px; font-size:11px; background:#2b2b2b; }"
            "QPushButton:checked { background:#3a4a6a; border-color:#5599ff; color:#fff; }"
            "QPushButton:hover:!checked { background:#333; }"
        )
        labels = [
            ("All",   "All"),
            ("1",     "1P"), ("2", "2P"), ("3", "3P"),
            ("4",     "4P"), ("5", "5P"), ("6", "6P"),
            ("Title", "Title"),
            ("Saved", "\u2605 Saved"),
        ]
        for key, display in labels:
            btn = QPushButton(display)
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setStyleSheet(_TAB_STYLE)
            btn.clicked.connect(lambda _, k=key: self._on_filter(k))
            self._filter_group.addButton(btn)
            tab_bar.addWidget(btn)
            if key == "All":
                btn.setChecked(True)
        tab_bar.addStretch()
        root.addLayout(tab_bar)

        # Scroll grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(6)
        self._scroll.setWidget(self._grid_container)
        root.addWidget(self._scroll, stretch=1)

        self._status = QLabel("No layout selected — click a thumbnail to choose one.")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet("color:#888; font-size:10px; padding:2px;")
        root.addWidget(self._status)

    def _populate_grid(self, key: str):
        for t in self._thumbs:
            t.setParent(None)
        self._thumbs.clear()

        filtered = self._filter_layouts(key)
        cols = 4
        for i, layout in enumerate(filtered):
            t = LayoutThumb(layout)
            t.clicked.connect(self._on_thumb_clicked)
            t.double_clicked.connect(self._on_thumb_double_clicked)
            self._grid.addWidget(t, i // cols, i % cols)
            self._thumbs.append(t)
            if self._selected_layout and layout.get("path") and \
                    layout["path"] == self._selected_layout.get("path"):
                t.set_selected(True)
                self._selected_thumb = t

        remainder = len(filtered) % cols
        if filtered and remainder:
            for j in range(cols - remainder):
                sp = QWidget()
                sp.setFixedSize(THUMB_W + 8, THUMB_H + 28)
                self._grid.addWidget(sp, len(filtered) // cols, remainder + j)

    def _filter_layouts(self, key: str) -> list:
        if key == "All":    return self._all_layouts
        if key == "Title":  return [l for l in self._all_layouts if l["is_title"]]
        if key == "Saved":  return [l for l in self._all_layouts if l.get("is_user")]
        try:
            n = int(key)
            return [l for l in self._all_layouts if l["frames"] == n and not l["is_title"]]
        except ValueError:
            return self._all_layouts

    def _on_filter(self, key: str):
        self._current_filter = key
        self._populate_grid(key)

    def _on_thumb_clicked(self, layout: dict):
        if self._selected_thumb:
            self._selected_thumb.set_selected(False)
        for t in self._thumbs:
            if t._layout.get("path") == layout.get("path"):
                t.set_selected(True)
                self._selected_thumb = t
                break
        self._selected_layout = layout
        n = layout["frames"]
        self._status.setText(
            f"Selected: {layout['name']}  ({n} panel{'s' if n!=1 else ''})"
            " — double-click to confirm"
        )
        self.layout_selected.emit(layout)

    def _on_thumb_double_clicked(self, layout: dict):
        self._on_thumb_clicked(layout)
        self._status.setText(f"\u2713 Confirmed: {layout['name']}")
        self.layout_confirmed.emit(layout)
