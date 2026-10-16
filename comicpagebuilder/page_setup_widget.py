"""
page_setup_widget.py - Tab 0: Page Setup
"""
import json
import os
from PyQt5.QtWidgets import (
    QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QComboBox, QDoubleSpinBox, QSpinBox,
    QLabel, QPushButton, QInputDialog, QMessageBox,
)
from PyQt5.QtCore import pyqtSignal, Qt
from .utils import PageSpec

_DATA_DIR          = os.path.join(os.path.dirname(__file__), "resources", "data")
_PAPER_SIZES_FILE  = os.path.join(_DATA_DIR, "papersizes.json")
_USER_PRESETS_FILE = os.path.join(_DATA_DIR, "user_presets.json")

def _load_paper_sizes() -> dict:
    sizes = {}
    if os.path.exists(_USER_PRESETS_FILE):
        try:
            with open(_USER_PRESETS_FILE, "r", encoding="utf-8") as f:
                for entry in json.load(f):
                    sizes[f"★ {entry['name']}"] = {"width": entry["width"], "height": entry["height"]}
        except Exception:
            pass
    if os.path.exists(_PAPER_SIZES_FILE):
        try:
            with open(_PAPER_SIZES_FILE, "r", encoding="utf-8") as f:
                for entry in json.load(f):
                    sizes[entry["name"]] = {"width": entry["width"], "height": entry["height"]}
        except Exception:
            pass
    if not sizes:
        sizes = {"Commercial": {"width": 220, "height": 310}, "ISO A4": {"width": 210, "height": 297}}
    sizes["Custom"] = None
    return sizes

def _save_user_preset(name: str, w: float, h: float):
    presets = []
    if os.path.exists(_USER_PRESETS_FILE):
        try:
            with open(_USER_PRESETS_FILE, "r", encoding="utf-8") as f:
                presets = json.load(f)
        except Exception:
            presets = []
    presets = [p for p in presets if p["name"] != name]
    presets.append({"name": name, "width": w, "height": h})
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_USER_PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2)

def _mm_spin(min_val, max_val, default, decimals=2) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(min_val, max_val)
    spin.setValue(default)
    spin.setDecimals(decimals)
    spin.setSuffix(" mm")
    spin.setSingleStep(0.5)
    return spin

class _LockedPair(QWidget):
    value_changed = pyqtSignal()
    def __init__(self, default_w=210.0, default_h=297.0, parent=None):
        super().__init__(parent)
        self._ratio    = default_h / default_w if default_w else 1.0
        self._locked   = False
        self._updating = False

        self._spin_w = _mm_spin(20, 1000, default_w)
        self._spin_h = _mm_spin(20, 1000, default_h)
        self._spin_w.valueChanged.connect(self._on_w)
        self._spin_h.valueChanged.connect(self._on_h)

        self._lock_btn = QPushButton("🔓")
        self._lock_btn.setCheckable(True)
        self._lock_btn.setFixedSize(28, 28)
        self._lock_btn.setToolTip("Lock aspect ratio")
        self._lock_btn.setStyleSheet(
            "QPushButton { font-size:13px; padding:0; border:1px solid #555; border-radius:4px; }"
            "QPushButton:checked { background:#3a3a5a; border-color:#88aaff; }"
        )
        self._lock_btn.toggled.connect(self._on_lock)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(4)
        grid.addWidget(QLabel("Width (mm):"),  0, 0, Qt.AlignRight)
        grid.addWidget(self._spin_w,           0, 1)
        grid.addWidget(self._lock_btn,         0, 2, 2, 1, Qt.AlignVCenter)
        grid.addWidget(QLabel("Height (mm):"), 1, 0, Qt.AlignRight)
        grid.addWidget(self._spin_h,           1, 1)
        grid.setColumnStretch(1, 1)

    def width_value(self)  -> float: return self._spin_w.value()
    def height_value(self) -> float: return self._spin_h.value()

    def set_values(self, w: float, h: float):
        self._updating = True
        self._spin_w.setValue(w)
        self._spin_h.setValue(h)
        self._ratio = h / w if w else 1.0
        self._updating = False
        self.value_changed.emit()

    def set_unit(self, ratio: float, suffix: str, decimals: int):
        self._updating = True
        self._spin_w.setRange(self._spin_w.minimum() * ratio, self._spin_w.maximum() * ratio)
        self._spin_h.setRange(self._spin_h.minimum() * ratio, self._spin_h.maximum() * ratio)
        self._spin_w.setDecimals(decimals)
        self._spin_h.setDecimals(decimals)
        self._spin_w.setSuffix(suffix)
        self._spin_h.setSuffix(suffix)
        self._spin_w.setValue(self._spin_w.value() * ratio)
        self._spin_h.setValue(self._spin_h.value() * ratio)
        self._updating = False

    def block(self, yes: bool):
        self._spin_w.blockSignals(yes)
        self._spin_h.blockSignals(yes)

    def _on_lock(self, locked: bool):
        self._locked = locked
        self._lock_btn.setText("🔒" if locked else "🔓")
        if locked:
            w = self._spin_w.value()
            self._ratio = self._spin_h.value() / w if w else 1.0

    def _on_w(self, val: float):
        if self._updating: return
        if self._locked and val > 0:
            self._updating = True
            self._spin_h.setValue(round(val * self._ratio, 2))
            self._updating = False
        self.value_changed.emit()

    def _on_h(self, val: float):
        if self._updating: return
        if self._locked and val > 0:
            self._updating = True
            self._spin_w.setValue(round(val / self._ratio, 2))
            self._updating = False
        self.value_changed.emit()

class PageSetupWidget(QWidget):
    spec_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paper_sizes      = _load_paper_sizes()
        self._suppress_signals = False
        self._unit_factor      = 1.0   
        self._current_unit     = "mm"

        self._build_ui()
        self._populate_paper_dropdown()
        self._apply_preset(list(self._paper_sizes.keys())[0])

    def get_spec(self) -> PageSpec:
        f = self._unit_factor
        spec = PageSpec()
        spec.manuscript_w  = self._manuscript_pair.width_value()  * f
        spec.manuscript_h  = self._manuscript_pair.height_value() * f
        spec.binding_w     = self._binding_pair.width_value()     * f
        spec.binding_h     = self._binding_pair.height_value()    * f
        spec.bleed         = self._bleed.value()         * f
        spec.safe_area     = self._safe_area.value()     * f
        spec.resolution    = self._resolution.value()
        spec.orientation   = "landscape" if self._orientation.currentIndex() == 1 else "portrait"
        spec.margins       = self._margins.value()       * f
        spec.line_strength = self._line_strength.value() * f
        spec.colorspace    = self._colorspace_combo.currentData()
        return spec

    def set_spec(self, spec: PageSpec):
        self._suppress_signals = True
        f = self._unit_factor
        self._manuscript_pair.set_values(spec.manuscript_w / f, spec.manuscript_h / f)
        self._binding_pair.set_values(spec.binding_w / f, spec.binding_h / f)
        self._bleed.setValue(spec.bleed / f)
        self._safe_area.setValue(getattr(spec, 'safe_area', 5.0) / f)
        self._resolution.setValue(spec.resolution)
        self._orientation.setCurrentIndex(1 if spec.orientation == "landscape" else 0)
        self._orient_portrait_btn.setChecked(spec.orientation == "portrait")
        self._orient_landscape_btn.setChecked(spec.orientation == "landscape")
        self._margins.setValue(spec.margins / f)
        self._line_strength.setValue(spec.line_strength / f)
        
        idx = self._colorspace_combo.findData(getattr(spec, "colorspace", "RGBA"))
        if idx >= 0:
            self._colorspace_combo.setCurrentIndex(idx)
            
        self._suppress_signals = False
        self.spec_changed.emit()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        preset_group  = QGroupBox("Paper Preset")
        preset_layout = QVBoxLayout(preset_group)
        combo_row = QHBoxLayout()
        combo_row.setSpacing(6)
        combo_row.addWidget(QLabel("Preset:"))
        self._preset_combo = QComboBox()
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        combo_row.addWidget(self._preset_combo, stretch=1)

        self._reset_btn = QPushButton("↺")
        self._reset_btn.setFixedWidth(28)
        self._reset_btn.setToolTip("Reset all fields to the selected preset's defaults")
        self._reset_btn.clicked.connect(self._on_reset_preset)
        combo_row.addWidget(self._reset_btn)

        self._save_btn = QPushButton("Save…")
        self._save_btn.setFixedWidth(52)
        self._save_btn.setToolTip("Save current binding size as a named preset")
        self._save_btn.clicked.connect(self._on_save_preset)
        combo_row.addWidget(self._save_btn)
        preset_layout.addLayout(combo_row)

        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("Units:"))
        self._unit_combo = QComboBox()
        self._unit_combo.addItems(["mm", "cm", "in"])
        self._unit_combo.setFixedWidth(60)
        self._unit_combo.currentTextChanged.connect(self._on_unit_changed)
        unit_row.addWidget(self._unit_combo)
        unit_row.addStretch()
        preset_layout.addLayout(unit_row)

        orient_row = QHBoxLayout()
        orient_row.addWidget(QLabel("Orientation:"))
        self._orientation = QComboBox()
        self._orientation.addItems(["Portrait", "Landscape"])
        self._orientation.setVisible(False)

        self._orient_portrait_btn  = QPushButton("▯  Portrait")
        self._orient_landscape_btn = QPushButton("▭  Landscape")
        for btn in (self._orient_portrait_btn, self._orient_landscape_btn):
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                "QPushButton { border:1px solid #555; border-radius:3px; padding:0 10px; background:#2b2b2b; }"
                "QPushButton:checked { background:#3a4a6a; border-color:#5599ff; color:#fff; }"
                "QPushButton:hover:!checked { background:#333; }"
            )
        self._orient_portrait_btn.setChecked(True)
        self._orient_portrait_btn.clicked.connect(lambda: self._set_orientation("portrait"))
        self._orient_landscape_btn.clicked.connect(lambda: self._set_orientation("landscape"))

        orient_row.addWidget(self._orient_portrait_btn)
        orient_row.addWidget(self._orient_landscape_btn)
        orient_row.addStretch()
        preset_layout.addLayout(orient_row)
        root.addWidget(preset_group)

        ms_group  = QGroupBox("Manuscript Size (full canvas, including bleed)")
        ms_layout = QVBoxLayout(ms_group)
        self._manuscript_pair = _LockedPair(default_w=220.0, default_h=310.0)
        self._manuscript_pair.value_changed.connect(self._emit)
        ms_layout.addWidget(self._manuscript_pair)
        root.addWidget(ms_group)

        bd_group  = QGroupBox("Binding Size (finished / trimmed page)")
        bd_layout = QVBoxLayout(bd_group)
        self._binding_pair = _LockedPair(default_w=210.0, default_h=297.0)
        self._binding_pair.value_changed.connect(self._emit)
        bd_layout.addWidget(self._binding_pair)
        root.addWidget(bd_group)

        # ---- Bleed & Safe Area ----
        bleed_group = QGroupBox("Bleed & Safe Area Settings")
        bleed_root  = QVBoxLayout(bleed_group)

        bleed_row = QHBoxLayout()
        bleed_row.addWidget(QLabel("Bleed:"))
        self._bleed = _mm_spin(0, 50, 5, decimals=1)
        self._bleed.valueChanged.connect(self._on_bleed_changed)
        bleed_row.addWidget(self._bleed, stretch=1)

        bleed_row.addWidget(QLabel("  Safe Area:"))
        self._safe_area = _mm_spin(0, 50, 5, decimals=1)
        self._safe_area.valueChanged.connect(self._emit)
        bleed_row.addWidget(self._safe_area, stretch=1)

        # Link toggle — when active, safe area = bleed + 2mm automatically
        self._safe_link_btn = QPushButton("🔗")
        self._safe_link_btn.setCheckable(True)
        self._safe_link_btn.setChecked(True)
        self._safe_link_btn.setFixedSize(28, 28)
        self._safe_link_btn.setToolTip(
            "Auto-link: safe area = bleed + 2mm\n"
            "Click to unlock and set manually"
        )
        self._safe_link_btn.setStyleSheet(
            "QPushButton { font-size:13px; padding:0; border:1px solid #555; border-radius:4px; }"
            "QPushButton:checked { background:#3a3a5a; border-color:#88aaff; }"
        )
        bleed_row.addWidget(self._safe_link_btn)
        bleed_root.addLayout(bleed_row)

        bleed_quick = QHBoxLayout()
        bleed_quick.setSpacing(4)
        bleed_quick.addWidget(QLabel("Bleed quick:"))
        for val, label in [(0, "0"), (3, "3mm"), (5, "5mm"), (10, "10mm")]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "QPushButton { font-size:9px; border:1px solid #555; border-radius:3px;"
                " padding:0 4px; background:#2b2b2b; }"
                "QPushButton:hover { background:#3a3a3a; }"
            )
            btn.clicked.connect(lambda _, v=val: self._bleed.setValue(v / self._unit_factor))
            bleed_quick.addWidget(btn)
        bleed_quick.addStretch()
        bleed_root.addLayout(bleed_quick)
        root.addWidget(bleed_group)

        res_group = QGroupBox("Resolution")
        res_root  = QVBoxLayout(res_group)
        res_row = QHBoxLayout()
        self._resolution = QSpinBox()
        self._resolution.setRange(72, 1200)
        self._resolution.setValue(300)
        self._resolution.setSuffix(" dpi")
        self._resolution.valueChanged.connect(self._emit)
        res_row.addWidget(self._resolution, stretch=1)
        res_root.addLayout(res_row)

        res_quick = QHBoxLayout()
        res_quick.setSpacing(4)
        res_quick.addWidget(QLabel("Quick:"))
        for dpi, label in [(72, "72 — Screen"), (150, "150"), (300, "300 — Print"), (600, "600 — HQ")]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "QPushButton { font-size:9px; border:1px solid #555; border-radius:3px;"
                " padding:0 4px; background:#2b2b2b; }"
                "QPushButton:hover { background:#3a3a3a; }"
            )
            btn.clicked.connect(lambda _, d=dpi: self._resolution.setValue(d))
            res_quick.addWidget(btn)
        res_quick.addStretch()
        res_root.addLayout(res_quick)
        root.addWidget(res_group)

        # ---- Panel Layout ----
        layout_group = QGroupBox("Panel Layout")
        layout_root  = QVBoxLayout(layout_group)

        margin_row = QHBoxLayout()
        self._margin_label = QLabel("Inner margin (mm):")
        margin_row.addWidget(self._margin_label)
        self._margins = _mm_spin(0, 50, 5, decimals=1)
        self._margins.valueChanged.connect(self._emit)
        margin_row.addWidget(self._margins)
        layout_root.addLayout(margin_row)

        margin_quick = QHBoxLayout()
        margin_quick.setSpacing(4)
        margin_quick.addWidget(QLabel("Quick:"))
        for val, label in [(0, "0"), (3, "3mm"), (5, "5mm"), (8, "8mm")]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "QPushButton { font-size:9px; border:1px solid #555; border-radius:3px;"
                " padding:0 4px; background:#2b2b2b; }"
                "QPushButton:hover { background:#3a3a3a; }"
            )
            btn.clicked.connect(lambda _, v=val: self._margins.setValue(v / self._unit_factor))
            margin_quick.addWidget(btn)
        margin_quick.addStretch()
        layout_root.addLayout(margin_quick)

        # Intelligent Margin Warning Label
        self._margin_warning = QLabel("⚠️ Margins are inside the print Safe Area. Risk of panels being cut off.")
        self._margin_warning.setStyleSheet("color: #ff8844; font-size: 10px; font-weight: bold;")
        self._margin_warning.setWordWrap(True)
        self._margin_warning.setVisible(False)
        layout_root.addWidget(self._margin_warning)

        line_row = QHBoxLayout()
        self._line_label = QLabel("Line strength (mm):")
        line_row.addWidget(self._line_label)
        self._line_strength = _mm_spin(0.1, 5.0, 0.5, decimals=2)
        self._line_strength.valueChanged.connect(self._emit)
        line_row.addWidget(self._line_strength)
        layout_root.addLayout(line_row)

        line_quick = QHBoxLayout()
        line_quick.setSpacing(4)
        line_quick.addWidget(QLabel("Quick:"))
        for val, label in [(0.25, "0.25 — Thin"), (0.5, "0.5"), (1.0, "1mm — Bold"), (2.0, "2mm — Heavy")]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "QPushButton { font-size:9px; border:1px solid #555; border-radius:3px;"
                " padding:0 4px; background:#2b2b2b; }"
                "QPushButton:hover { background:#3a3a3a; }"
            )
            btn.clicked.connect(lambda _, v=val: self._line_strength.setValue(v / self._unit_factor))
            line_quick.addWidget(btn)
        line_quick.addStretch()
        layout_root.addLayout(line_quick)

        line_hint = QLabel("Line strength affects panel borders only — guides are always hairline.")
        line_hint.setStyleSheet("color:#555; font-size:9px;")
        line_hint.setWordWrap(True)
        layout_root.addWidget(line_hint)
        root.addWidget(layout_group)

        cs_group = QGroupBox("Color Space")
        cs_form  = QFormLayout(cs_group)
        self._colorspace_combo = QComboBox()
        for label, key in [
            ("RGB/A 8-bit", "RGBA"), ("RGB/A 16-bit", "RGBA16"),
            ("Gray/A 8-bit", "GRAYA"), ("CMYK/A 8-bit", "CMYK"),
        ]:
            self._colorspace_combo.addItem(label, key)
        self._colorspace_combo.currentIndexChanged.connect(self._emit)
        cs_form.addRow("Model:", self._colorspace_combo)
        root.addWidget(cs_group)
        root.addStretch()

    def _populate_paper_dropdown(self):
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        for name in self._paper_sizes:
            self._preset_combo.addItem(name)
        self._preset_combo.blockSignals(False)

    def _apply_preset(self, name: str):
        data = self._paper_sizes.get(name)
        if data is None: return
        self._suppress_signals = True
        w, h = data["width"], data["height"]
        
        _defaults = PageSpec()
        f     = self._unit_factor
        bleed = _defaults.bleed / f
        self._bleed.setValue(bleed)
        self._safe_area.setValue(_defaults.safe_area / f)
        self._margins.setValue(_defaults.margins / f)
        self._line_strength.setValue(_defaults.line_strength / f)
        
        w_d = w / f
        h_d = h / f
        
        self._manuscript_pair.block(True)
        self._binding_pair.block(True)
        self._manuscript_pair.set_values(w_d + bleed * 2, h_d + bleed * 2)
        self._binding_pair.set_values(w_d, h_d)
        self._manuscript_pair.block(False)
        self._binding_pair.block(False)
        
        self._suppress_signals = False
        self._emit()

    def _on_bleed_changed(self, _=None):
        """When bleed changes, auto-update safe area if the link is active."""
        if self._safe_link_btn.isChecked():
            bleed_mm = self._bleed.value() * self._unit_factor
            safe_mm  = max(bleed_mm + 2.0, 3.0)
            # Set without triggering another bleed_changed
            self._safe_area.blockSignals(True)
            self._safe_area.setValue(safe_mm / self._unit_factor)
            self._safe_area.blockSignals(False)
        self._emit()

    def _on_preset_changed(self, name: str):
        self._apply_preset(name)

    def _on_reset_preset(self):
        self._apply_preset(self._preset_combo.currentText())

    def _on_unit_changed(self, new_unit: str):
        _factors = {"mm": 1.0, "cm": 10.0, "in": 25.4}
        new_f = _factors.get(new_unit, 1.0)
        ratio = self._unit_factor / new_f
        decimals = {"mm": 2, "cm": 3, "in": 4}.get(new_unit, 2)
        suffix   = f" {new_unit}"
        
        self._suppress_signals = True
        self._manuscript_pair.set_unit(ratio, suffix, decimals)
        self._binding_pair.set_unit(ratio, suffix, decimals)
        
        for spin in (self._bleed, self._safe_area, self._margins, self._line_strength):
            spin.setRange(spin.minimum() * ratio, spin.maximum() * ratio)
            spin.setDecimals(decimals + 1)
            spin.setValue(spin.value() * ratio)
            spin.setSuffix(suffix)
            
        self._unit_factor  = new_f
        self._current_unit = new_unit
        self._margin_label.setText(f"Inner margin ({new_unit}):")
        self._line_label.setText(f"Line strength ({new_unit}):")
        self._suppress_signals = False
        self._emit()

    def _on_save_preset(self):
        w_d = self._binding_pair.width_value()
        h_d = self._binding_pair.height_value()
        w   = w_d * self._unit_factor
        h   = h_d * self._unit_factor
        name, ok = QInputDialog.getText(
            self, "Save Preset", f"Name for this preset ({w_d:.2f} × {h_d:.2f} {self._current_unit}):"
        )
        if not ok or not name.strip(): return
        name = name.strip()
        _save_user_preset(name, w, h)
        self._paper_sizes = _load_paper_sizes()
        self._populate_paper_dropdown()
        idx = self._preset_combo.findText(f"★ {name}")
        if idx >= 0:
            self._preset_combo.blockSignals(True)
            self._preset_combo.setCurrentIndex(idx)
            self._preset_combo.blockSignals(False)
        QMessageBox.information(self, "Saved", f'"{name}" saved as a preset.')

    def _set_orientation(self, mode: str):
        self._orient_portrait_btn.setChecked(mode == "portrait")
        self._orient_landscape_btn.setChecked(mode == "landscape")
        self._orientation.setCurrentIndex(0 if mode == "portrait" else 1)
        self._emit()

    def _emit(self, *_):
        if not self._suppress_signals:
            # Intelligent Warning Logic Check
            margin = self._margins.value() * self._unit_factor
            safe = self._safe_area.value() * self._unit_factor
            
            # Show warning if margins are greater than 0 but strictly smaller than the safe area
            if 0 < margin <= safe:
                self._margin_warning.setVisible(True)
            else:
                self._margin_warning.setVisible(False)
                
            self.spec_changed.emit()