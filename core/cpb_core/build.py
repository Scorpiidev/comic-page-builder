"""
Make pages from layout recipes.

Each function records its recipe in ``Page.layout``, so the page can be
rebuilt or re-flowed later (for example after changing the margins).
"""

from __future__ import annotations

import random
from typing import Iterable, Optional

from .geometry import PageGeometry, PageSize
from .layouts import bsp, grid
from .layouts.presets import Preset
from .model import Page, PanelStyle


def page_from_bsp(number: int, size: PageSize, panels: int, *, mode: str = "auto",
                  seed: Optional[int] = None, snap: bool = True, gutter: float = 3.0,
                  reading: str = "ltr", style: Optional[PanelStyle] = None) -> Page:
    """A random layout. A missing seed is picked now and stored, so it can be locked."""
    if seed is None:
        seed = random.randrange(10_000, 100_000)
    live = PageGeometry.of(size).live
    cells = bsp.generate(panels, live.w, live.h, mode=mode, seed=seed, snap=snap)
    recipe = {"kind": "bsp", "panels": panels, "mode": mode, "seed": seed, "snap": snap}
    return Page(number, size, tuple(cells), gutter, reading, style or PanelStyle(), recipe)


def page_manual(number: int, size: PageSize, layout: Optional[dict] = None, *, gutter: float = 3.0,
                reading: str = "ltr", style: Optional[PanelStyle] = None) -> Page:
    """A hand-made layout (layouts/knife.py); without ``layout``, one blank panel to cut up."""
    from .layouts.knife import empty
    return Page(number, size, (), gutter, reading, style or PanelStyle(), layout or empty())


def page_from_preset(number: int, size: PageSize, preset: Preset, *, gutter: float = 3.0,
                     reading: str = "ltr", style: Optional[PanelStyle] = None) -> Page:
    recipe = {"kind": "preset", "name": preset.name}
    return Page(number, size, preset.cells, gutter, reading, style or PanelStyle(), recipe)


def page_from_grid(number: int, size: PageSize, rows: int, cols: int,
                   merges: Iterable = (), *, gutter: float = 3.0, reading: str = "ltr",
                   style: Optional[PanelStyle] = None) -> Page:
    merges = [tuple(map(tuple, m)) for m in merges]
    cells = grid.grid_cells(rows, cols, merges)
    recipe = {"kind": "grid", "rows": rows, "cols": cols, "merges": [list(map(list, m)) for m in merges]}
    return Page(number, size, tuple(cells), gutter, reading, style or PanelStyle(), recipe)


def rebuild(page: Page, size: Optional[PageSize] = None) -> Page:
    """
    Recompute a page's cells from its recipe (for example on a new page size).

    BSP pages keep their seed, so the layout keeps its character. Pages with
    no recipe (hand-made cells) keep their cells as they are.
    """
    size = size or page.size
    r = page.layout
    if r.get("kind") == "bsp":
        return page_from_bsp(page.number, size, r["panels"], mode=r["mode"], seed=r["seed"],
                             snap=r["snap"], gutter=page.gutter, reading=page.reading, style=page.style)
    return Page(page.number, size, page.cells, page.gutter, page.reading, page.style, dict(r))


BATCH_MODES = ("auto", "mixed", "chaos", "same")


def plan_batch(count: int, *, mode: str = "auto", min_panels: int = 4, max_panels: int = 6,
               seed: Optional[int] = None, same_as: Optional[dict] = None) -> list[dict]:
    """
    Recipes for a batch of BSP pages: one dict per page with panels, mode and seed.

    mode:
        ``"auto"`` / ``"chaos"``  every page uses that cut mode
        ``"mixed"``               each page picks auto, rows or cols
        ``"same"``                every page copies ``same_as`` (a page's layout recipe)
    The same ``seed`` always gives the same batch.
    """
    if not 1 <= count <= 50:
        raise ValueError("a batch is 1 to 50 pages")
    if mode not in BATCH_MODES:
        raise ValueError(f"batch mode must be one of {BATCH_MODES}")
    if mode == "same":
        if not same_as or same_as.get("kind") != "bsp":
            raise ValueError("'same' needs a random-layout page to copy")
        return [dict(panels=same_as["panels"], mode=same_as["mode"], seed=same_as["seed"],
                     snap=same_as.get("snap", True)) for _ in range(count)]
    lo, hi = sorted((min_panels, max_panels))
    rng = random.Random(seed)
    plan = []
    for _ in range(count):
        cut = rng.choice(("auto", "rows", "cols")) if mode == "mixed" else mode
        page_seed = rng.randrange(10_000, 100_000)
        plan.append(dict(panels=rng.randint(lo, hi), mode=cut, seed=page_seed, snap=True))
    return plan
