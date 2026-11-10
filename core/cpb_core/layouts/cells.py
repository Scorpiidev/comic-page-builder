"""Cells: gutter-free layout rectangles, plus reading order and gutters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..geometry import Rect

EPS = 1e-6


@dataclass(frozen=True)
class Cell:
    """A panel slot in 0..1 coordinates of the live area."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return self.w * self.h

    def as_rect(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)


def reading_order(cells: Iterable[Cell], direction: str = "ltr",
                  row_tolerance: float = 0.02) -> list[Cell]:
    """
    Sort cells the way a reader's eye travels.

    Cells whose tops are within ``row_tolerance`` of each other form a row.
    Rows go top to bottom; inside a row, cells go left to right (``"ltr"``)
    or right to left for manga (``"rtl"``). A tall panel that spans two rows
    is read with the row its top starts in.
    """
    if direction not in ("ltr", "rtl"):
        raise ValueError("direction must be 'ltr' or 'rtl'")
    remaining = sorted(cells, key=lambda c: (c.y, c.x))
    ordered: list[Cell] = []
    while remaining:
        top = remaining[0].y
        row = [c for c in remaining if c.y - top <= row_tolerance]
        remaining = [c for c in remaining if c.y - top > row_tolerance]
        row.sort(key=lambda c: c.x, reverse=(direction == "rtl"))
        ordered.extend(row)
    return ordered


def apply_gutter(cells: Sequence[Cell], live: Rect, gutter_mm: float) -> list[Rect]:
    """
    Turn cells into panel rectangles in millimetres.

    Each edge that touches another cell moves in by half the gutter, so two
    neighbours end up exactly ``gutter_mm`` apart. Edges on the live-area
    border stay put, so the outer panels line up with the margins.
    """
    if gutter_mm < 0:
        raise ValueError("gutter can't be negative")
    gx = gutter_mm / live.w / 2
    gy = gutter_mm / live.h / 2
    out = []
    for c in cells:
        x0 = c.x + (gx if c.x > EPS else 0.0)
        x1 = c.right - (gx if c.right < 1 - EPS else 0.0)
        y0 = c.y + (gy if c.y > EPS else 0.0)
        y1 = c.bottom - (gy if c.bottom < 1 - EPS else 0.0)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("the gutter is wider than a panel")
        out.append(Rect(live.x + x0 * live.w, live.y + y0 * live.h,
                        (x1 - x0) * live.w, (y1 - y0) * live.h))
    return out


def coverage(cells: Iterable[Cell]) -> float:
    """Total area of the cells (1.0 means they fill the live area, if none overlap)."""
    return sum(c.area for c in cells)


def overlaps(cells: Sequence[Cell], tol: float = 1e-6) -> list[tuple[int, int]]:
    """Index pairs of cells that overlap by more than ``tol`` of the page area."""
    found = []
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            if cells[i].as_rect().intersection_area(cells[j].as_rect()) > tol:
                found.append((i, j))
    return found
