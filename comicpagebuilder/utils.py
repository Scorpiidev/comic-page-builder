"""
utils.py — unit conversions and shared data types.

All internal geometry is kept in points (pt, 1/72 inch) matching how
Krita's vector layer SVG coordinate system works. Pixels are only used
when talking to the Krita document API (width/height/resolution).
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------

MM_TO_PT  = 72.0 / 25.4   # 1 mm in points
MM_TO_IN  = 1.0  / 25.4   # 1 mm in inches


def mm_to_pt(mm: float) -> float:
    return mm * MM_TO_PT


def pt_to_mm(pt: float) -> float:
    return pt / MM_TO_PT


def mm_to_px(mm: float, dpi: int) -> int:
    return round(mm * dpi / 25.4)


def px_to_mm(px: int, dpi: int) -> float:
    return px * 25.4 / dpi


# ---------------------------------------------------------------------------
# PageSpec — the single object that flows between all widgets and the builder
# ---------------------------------------------------------------------------

@dataclass
class PageSpec:
    """
    Everything needed to generate one comic page.

    All size values are in millimetres; the builder converts as needed.
    """

    # --- Paper / canvas ---
    manuscript_w: float = 220.0   # full bleed sheet width  (mm)
    manuscript_h: float = 310.0   # full bleed sheet height (mm)

    # --- Finished (binding) size — the printed area inside the bleed ---
    binding_w: float = 210.0      # finished width  (mm)
    binding_h: float = 297.0      # finished height (mm)  (A4 default)

    # --- Bleed ---
    bleed: float = 5.0            # bleed width on each side (mm)
    safe_area: float = 5.0        # safe zone inside binding (mm)

    # --- Document settings ---
    resolution: int = 300         # DPI
    orientation: str = "portrait" # "portrait" | "landscape"

    # --- Layout ---
    layout_file: Optional[str] = None   # path to the chosen JSON layout
    margins: float = 5.0                # inner panel margins (mm)
    line_strength: float = 0.5          # panel border thickness (mm)

    # --- Color space ---
    colorspace: str = "RGBA"   # RGBA | RGBA16 | RGBA32 | GRAYA | GRAYA16 | CMYK
    # (used by document_builder to pick model + depth + profile)

    # --- Project metadata (used by project_widget) ---
    page_number: int = 1
    label: str = ""

    # --- Derived helpers ---

    def canvas_width_px(self) -> int:
        return mm_to_px(self.manuscript_w, self.resolution)

    def canvas_height_px(self) -> int:
        return mm_to_px(self.manuscript_h, self.resolution)

    def is_landscape(self) -> bool:
        return self.orientation == "landscape"

    def effective_manuscript_w(self) -> float:
        """Return manuscript_w, swapped if landscape."""
        if self.is_landscape():
            return max(self.manuscript_w, self.manuscript_h)
        return min(self.manuscript_w, self.manuscript_h)

    def effective_manuscript_h(self) -> float:
        if self.is_landscape():
            return min(self.manuscript_w, self.manuscript_h)
        return max(self.manuscript_w, self.manuscript_h)

    def effective_binding_w(self) -> float:
        if self.is_landscape():
            return max(self.binding_w, self.binding_h)
        return min(self.binding_w, self.binding_h)

    def effective_binding_h(self) -> float:
        if self.is_landscape():
            return min(self.binding_w, self.binding_h)
        return max(self.binding_w, self.binding_h)
