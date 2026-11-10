"""
Panel layouts.

A layout is a list of ``Cell``s: rectangles in 0..1 coordinates of the live
area that tile it with **no gutters**. Gutters are applied at build time by
``apply_gutter``, so one gutter setting works for presets, random layouts and
grid layouts alike, and changing it never changes a layout's shape.
"""

from .cells import Cell, apply_gutter, coverage, overlaps, reading_order
from .bsp import MODES, generate
from .presets import Preset, close_gutters, load_preset, load_presets
from .grid import NonRectangularMerge, grid_cells

__all__ = [
    "Cell", "apply_gutter", "coverage", "overlaps", "reading_order",
    "MODES", "generate",
    "Preset", "close_gutters", "load_preset", "load_presets",
    "NonRectangularMerge", "grid_cells",
]
