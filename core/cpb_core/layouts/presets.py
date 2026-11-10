"""
Preset layouts.

The bundled presets come from ComicCreator (GPL-3.0) and store rectangles
with the gutters baked in. ``close_gutters`` removes those gaps so the presets
become gutter-free cells like every other layout.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Iterable

from .cells import EPS, Cell


@dataclass(frozen=True)
class Preset:
    name: str
    cells: tuple[Cell, ...]
    tags: tuple[str, ...] = ()
    source: str = ""

    @property
    def panel_count(self) -> int:
        return len(self.cells)

    @property
    def is_title(self) -> bool:
        return "Title" in self.tags or self.name.lower().startswith("title")


def _vertical_overlap(a: list[float], b: list[float]) -> float:
    return min(a[3], b[3]) - max(a[1], b[1])


def _horizontal_overlap(a: list[float], b: list[float]) -> float:
    return min(a[2], b[2]) - max(a[0], b[0])


def close_gutters(rects: Iterable[dict], max_gap: float = 0.05) -> list[Cell]:
    """
    Turn rectangles with baked-in gutters into cells that touch.

    Two neighbours separated by a gap of at most ``max_gap`` (in page
    fractions) both move to the middle of the gap. Edges within ``max_gap``
    of the page border snap to it.
    """
    boxes = [[r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]] for r in rects]
    new = [b[:] for b in boxes]
    for i, a in enumerate(boxes):
        for j, b in enumerate(boxes):
            if i == j:
                continue
            gap_x = b[0] - a[2]
            if 0 < gap_x <= max_gap and _vertical_overlap(a, b) > EPS:
                mid = (a[2] + b[0]) / 2
                new[i][2] = mid
                new[j][0] = mid
            gap_y = b[1] - a[3]
            if 0 < gap_y <= max_gap and _horizontal_overlap(a, b) > EPS:
                mid = (a[3] + b[1]) / 2
                new[i][3] = mid
                new[j][1] = mid
    cells = []
    for x0, y0, x1, y1 in new:
        x0 = 0.0 if x0 <= max_gap / 2 else x0
        y0 = 0.0 if y0 <= max_gap / 2 else y0
        x1 = 1.0 if x1 >= 1 - max_gap / 2 else x1
        y1 = 1.0 if y1 >= 1 - max_gap / 2 else y1
        cells.append(Cell(round(x0, 6), round(y0, 6), round(x1 - x0, 6), round(y1 - y0, 6)))
    return cells


def load_preset(path: str) -> Preset:
    """Read one ComicCreator-style layout JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rects = [item["data"] for item in data.get("layout", []) if item.get("type") == "rect"]
    if not rects:
        raise ValueError("the file has no rectangles in its 'layout' list")
    name = os.path.splitext(os.path.basename(path))[0]
    return Preset(name=name, cells=tuple(close_gutters(rects)),
                  tags=tuple(data.get("tags", ())), source=path)


@dataclass
class LoadResult:
    presets: list[Preset] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (file name, reason)


def load_presets(folder: str) -> LoadResult:
    """
    Load every ``.json`` layout in a folder, in name order.

    Broken files don't stop the others from loading; they are reported in
    ``errors`` so the UI can say which file failed and why.
    """
    result = LoadResult()
    if not os.path.isdir(folder):
        return result
    for fname in sorted(os.listdir(folder)):
        if not fname.lower().endswith(".json"):
            continue
        try:
            result.presets.append(load_preset(os.path.join(folder, fname)))
        except (OSError, ValueError, KeyError, TypeError) as e:
            result.errors.append((fname, str(e)))
    return result
