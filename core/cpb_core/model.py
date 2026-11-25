"""
The page model: everything the hub knows about one comic page.

A ``Page`` stores *what was decided* (size, cells, gutter, style, and how the
layout was made). Panel rectangles are always derived from that, never
stored, so changing the gutter or margins can't leave stale geometry behind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .geometry import PageGeometry, PageSize, Rect
from .layouts.cells import Cell, apply_gutter, reading_order

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
CELL_DECIMALS = 6


@dataclass(frozen=True)
class PanelStyle:
    stroke: str = "#1b1b1b"
    stroke_width: float = 0.6   # mm
    fill: Optional[str] = None  # None = no fill (art shows through)
    corner_radius: float = 0.0  # mm

    def __post_init__(self) -> None:
        for name in ("stroke", "fill"):
            value = getattr(self, name)
            if value is not None and not _HEX.match(value):
                raise ValueError(f"{name} must be a colour like #1b1b1b, got {value!r}")
        if self.stroke_width < 0 or self.corner_radius < 0:
            raise ValueError("stroke width and corner radius can't be negative")


@dataclass(frozen=True)
class Panel:
    index: int  # 1-based, in reading order
    cell: Cell  # gutter-free slot in the live area (for a polygon: its bounding box)
    rect: Rect  # final rectangle in canvas mm, gutter applied (for a polygon: its bounding box)
    # Manual layouts (layouts/knife.py): the real outline in canvas mm, for
    # panels cut at an angle. None means the panel is just ``rect``.
    points: Optional[tuple] = None
    inset: int = -1  # the inset it belongs to (drawn over the others), or -1

    @property
    def on_top(self) -> bool:
        return self.inset >= 0


@dataclass
class Page:
    number: int
    size: PageSize
    cells: tuple[Cell, ...]
    gutter: float = 3.0
    reading: str = "ltr"  # "ltr" or "rtl" (manga)
    style: PanelStyle = field(default_factory=PanelStyle)
    # How the cells were made, so the hub can re-flow a locked layout.
    # e.g. {"kind": "bsp", "panels": 6, "mode": "auto", "seed": 48213, "snap": True}
    layout: dict = field(default_factory=dict)
    # The Letters layer's balloons (balloons.Balloon). None means "leave the
    # page's balloons as they are", so the page builder, which knows nothing
    # about balloons, can save a page without wiping its lettering.
    balloons: Optional[tuple] = None
    # Drawn pages (D7): the linked image under the letters (art.Art), else None.
    art: Optional[object] = None

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("page numbers start at 1")
        if self.reading not in ("ltr", "rtl"):
            raise ValueError("reading must be 'ltr' or 'rtl'")
        if self.gutter < 0:
            raise ValueError("gutter can't be negative")
        # Keep cells in reading order and at the precision page.svg stores
        # (6 decimals), so a page saved and read back compares equal.
        q = lambda v: round(v, CELL_DECIMALS)
        if self.layout.get("kind") == "manual":
            # Manual layouts are their cut tree; the cells are only bounding
            # boxes for page.svg's cpb:cell, so they're always derived from it.
            from .layouts.knife import shapes
            self.cells = tuple(s.bbox for s in shapes(self.layout))
        self.cells = tuple(reading_order((Cell(q(c.x), q(c.y), q(c.w), q(c.h)) for c in self.cells),
                                         self.reading))
        if self.balloons is not None:
            self.balloons = tuple(self.balloons)
            numbers = [b.number for b in self.balloons]
            if len(set(numbers)) != len(numbers):
                raise ValueError("two balloons on the page share a number")

    @property
    def is_art(self) -> bool:
        """A drawn page: its art came in as an image, so it has no generated panels."""
        return self.art is not None

    @property
    def file_name(self) -> str:
        return f"page_{self.number:02d}.svg"

    def geometry(self) -> PageGeometry:
        return PageGeometry.of(self.size)

    def panels(self) -> list[Panel]:
        if self.layout.get("kind") == "manual":
            from .layouts.knife import to_mm
            out = []
            for i, mp in enumerate(to_mm(self.layout, self.geometry().live, self.gutter, self.reading), start=1):
                xs, ys = [p[0] for p in mp.points], [p[1] for p in mp.points]
                rect = Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                out.append(Panel(i, mp.cell, rect, mp.points, mp.inset))
            return out
        rects = apply_gutter(self.cells, self.geometry().live, self.gutter)
        return [Panel(i, c, r) for i, (c, r) in enumerate(zip(self.cells, rects), start=1)]
