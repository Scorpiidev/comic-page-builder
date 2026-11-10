"""
Unit conversions.

The core stores every length in millimetres. Conversions happen only at the
edges: points when writing SVG or sizing type, pixels when an app needs a
canvas size, and display units (cm, in) in the UI.
"""

from __future__ import annotations

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
MM_PER_PT = MM_PER_INCH / PT_PER_INCH  # 0.3527... mm in one typographic point

# How many millimetres one display unit is worth.
MM_PER_UNIT = {
    "mm": 1.0,
    "cm": 10.0,
    "in": MM_PER_INCH,
    "pt": MM_PER_PT,
}


def mm_to_pt(mm: float) -> float:
    return mm / MM_PER_PT


def pt_to_mm(pt: float) -> float:
    return pt * MM_PER_PT


def mm_to_px(mm: float, dpi: int) -> int:
    """Whole pixels for a length at a resolution. Rounds to the nearest pixel."""
    return round(mm * dpi / MM_PER_INCH)


def px_to_mm(px: float, dpi: int) -> float:
    return px * MM_PER_INCH / dpi


def to_mm(value: float, unit: str) -> float:
    """Convert a value typed in a display unit into millimetres."""
    try:
        return value * MM_PER_UNIT[unit]
    except KeyError:
        raise ValueError(f"Unknown unit {unit!r}. Use one of: {', '.join(MM_PER_UNIT)}") from None


def from_mm(mm: float, unit: str) -> float:
    """Convert millimetres into a display unit. The stored value never changes."""
    try:
        return mm / MM_PER_UNIT[unit]
    except KeyError:
        raise ValueError(f"Unknown unit {unit!r}. Use one of: {', '.join(MM_PER_UNIT)}") from None
