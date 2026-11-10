"""
Seeded BSP (binary space partition) layout generator.

The same seed always gives the same layout, so the UI can lock a layout and
still change the gutter, page size or margins without re-rolling it.

Minimum panel sizes are measured in millimetres of the *live area* (not the
trim), so the limits you set are the limits you get.
"""

from __future__ import annotations

import random
from typing import Optional

from .cells import Cell

MODES = ("auto", "rows", "cols", "chaos")
MAX_PANELS = 8
SNAP_POINTS = (1 / 3, 1 / 2, 2 / 3)


def generate(n_panels: int, live_w_mm: float, live_h_mm: float, *,
             mode: str = "auto", seed: Optional[int] = None, snap: bool = True,
             min_w_mm: float = 30.0, min_h_mm: float = 40.0) -> list[Cell]:
    """
    Split the live area into up to ``n_panels`` cells.

    mode:
        ``"auto"``  cut the longer side (balanced, readable)
        ``"rows"``  horizontal cuts when possible
        ``"cols"``  vertical cuts when possible
        ``"chaos"`` random direction each time
    snap:
        prefer cuts at thirds and halves, which read as intentional.

    Returns fewer cells than asked for when the minimum panel size leaves no
    room. Callers should show ``len(result)``, not ``n_panels``.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if live_w_mm <= 0 or live_h_mm <= 0:
        raise ValueError("the live area must have a positive size")
    n_panels = max(1, min(MAX_PANELS, int(n_panels)))
    rng = random.Random(seed)
    min_w = min_w_mm / live_w_mm
    min_h = min_h_mm / live_h_mm

    leaves = [Cell(0.0, 0.0, 1.0, 1.0)]
    stuck: set[int] = set()  # indexes into ``leaves`` that couldn't be split

    while len(leaves) < n_panels:
        candidates = [i for i, c in enumerate(leaves)
                      if i not in stuck and (c.h >= 2 * min_h or c.w >= 2 * min_w)]
        if not candidates:
            break
        # Split the biggest panel (by real area, not normalised area).
        i = max(candidates, key=lambda k: leaves[k].w * live_w_mm * leaves[k].h * live_h_mm)
        t = leaves[i]
        can_h, can_v = t.h >= 2 * min_h, t.w >= 2 * min_w
        if can_h and not can_v:
            axis = "h"
        elif can_v and not can_h:
            axis = "v"
        elif mode == "rows":
            axis = "h"
        elif mode == "cols":
            axis = "v"
        elif mode == "auto":
            axis = "h" if t.h * live_h_mm >= t.w * live_w_mm else "v"
        else:
            axis = rng.choice(("h", "v"))

        span = t.h if axis == "h" else t.w
        lo = (min_h if axis == "h" else min_w) / span  # smallest allowed fraction
        f = None
        if snap:
            options = [p for p in SNAP_POINTS if lo <= p <= 1 - lo]
            if options:
                f = rng.choice(options)
        if f is None:
            f = lo + rng.random() * (1 - 2 * lo)
        if not lo <= f <= 1 - lo:
            stuck.add(i)
            continue

        if axis == "h":
            a = Cell(t.x, t.y, t.w, t.h * f)
            b = Cell(t.x, t.y + t.h * f, t.w, t.h * (1 - f))
        else:
            a = Cell(t.x, t.y, t.w * f, t.h)
            b = Cell(t.x + t.w * f, t.y, t.w * (1 - f), t.h)
        leaves[i:i + 1] = [a, b]
        # Indexes after ``i`` shifted by one; rebuild the stuck set to match.
        stuck = {k if k < i else k + 1 for k in stuck}

    return leaves
