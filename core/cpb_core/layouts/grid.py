"""
Grid layouts: start from rows x columns, merge neighbouring cells.

Merges are given as pairs of neighbouring grid positions. Each merged group
must form a rectangle; an L-shape raises ``NonRectangularMerge`` so the UI
can explain the problem instead of drawing overlapping panels.
(Polygon panels for L-shapes are planned; they need the polygon panel model.)
"""

from __future__ import annotations

from typing import Iterable

from .cells import Cell

Pos = tuple[int, int]  # (row, column)


class NonRectangularMerge(ValueError):
    def __init__(self, group: list[Pos]):
        self.group = sorted(group)
        super().__init__(f"merged cells {self.group} don't form a rectangle")


def grid_cells(rows: int, cols: int, merges: Iterable[tuple[Pos, Pos]] = ()) -> list[Cell]:
    """Cells for a ``rows`` x ``cols`` grid after applying ``merges``."""
    if rows < 1 or cols < 1:
        raise ValueError("a grid needs at least one row and one column")
    parent = {(r, c): (r, c) for r in range(rows) for c in range(cols)}

    def find(p: Pos) -> Pos:
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    for a, b in merges:
        if a not in parent or b not in parent:
            raise ValueError(f"{a} or {b} is outside the {rows}x{cols} grid")
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            raise ValueError(f"{a} and {b} aren't neighbours")
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    groups: dict[Pos, list[Pos]] = {}
    for p in parent:
        groups.setdefault(find(p), []).append(p)

    cells = []
    for members in groups.values():
        r0 = min(r for r, _ in members); r1 = max(r for r, _ in members)
        c0 = min(c for _, c in members); c1 = max(c for _, c in members)
        if (r1 - r0 + 1) * (c1 - c0 + 1) != len(members):
            raise NonRectangularMerge(members)
        cells.append(Cell(c0 / cols, r0 / rows, (c1 - c0 + 1) / cols, (r1 - r0 + 1) / rows))
    return cells
