"""
Command-line tool: build pages without the hub.

    python -m cpb_core papers
    python -m cpb_core build page_07.svg --paper "US Comic" --panels 6 --seed 48213
    python -m cpb_core build cover.svg --layout preset --preset title00
    python -m cpb_core build grid.svg --layout grid --grid 3x2 --merge 0,0:0,1
    python -m cpb_core batch Pages --count 8 --min-panels 4 --max-panels 6
    python -m cpb_core info page_07.svg
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from typing import Optional, Sequence

from .build import page_from_bsp, page_from_grid, page_from_preset
from .geometry import PageSize
from .layouts.bsp import MODES
from .layouts.presets import load_presets
from .model import Page, PanelStyle
from .paper import PAPER_SIZES, paper_size
from .svg import read_page, write_page

PAGE_FILE = re.compile(r"^page_(\d+)\.svg$", re.IGNORECASE)
DEFAULT_PRESET_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "comicpagebuilder", "resources", "layouts")


def _page_options(p: argparse.ArgumentParser) -> None:
    size = p.add_argument_group("page size (mm)")
    size.add_argument("--paper", default="US Comic", help="named trim size (see 'papers'); default: US Comic")
    size.add_argument("--trim", nargs=2, type=float, metavar=("W", "H"), help="custom trim size, overrides --paper")
    size.add_argument("--landscape", action="store_true")
    size.add_argument("--bleed", type=float, default=3.0)
    size.add_argument("--safe", type=float, default=5.0)
    size.add_argument("--margin", type=float, default=8.0)
    size.add_argument("--dpi", type=int, default=600)
    look = p.add_argument_group("panels")
    look.add_argument("--gutter", type=float, default=3.0)
    look.add_argument("--rtl", action="store_true", help="number panels right to left (manga)")
    look.add_argument("--stroke", default="#1b1b1b")
    look.add_argument("--stroke-width", type=float, default=0.6)
    look.add_argument("--fill", default="none", help="panel fill colour, or 'none'")
    look.add_argument("--radius", type=float, default=0.0, help="corner radius")


def _size(a: argparse.Namespace) -> PageSize:
    w, h = a.trim if a.trim else paper_size(a.paper)
    s = PageSize(trim_w=w, trim_h=h, bleed=a.bleed, safe=a.safe, margin=a.margin, dpi=a.dpi)
    return s.landscape() if a.landscape else s


def _style(a: argparse.Namespace) -> PanelStyle:
    return PanelStyle(stroke=a.stroke, stroke_width=a.stroke_width,
                      fill=None if a.fill.lower() == "none" else a.fill, corner_radius=a.radius)


def _merges(specs: Sequence[str]) -> list:
    out = []
    for s in specs:
        m = re.fullmatch(r"\s*(\d+),(\d+):(\d+),(\d+)\s*", s)
        if not m:
            raise ValueError(f"--merge {s!r} should look like 0,0:0,1 (row,col:row,col)")
        r1, c1, r2, c2 = map(int, m.groups())
        out.append(((r1, c1), (r2, c2)))
    return out


def _build_one(a: argparse.Namespace, number: int, seed: Optional[int], panels: Optional[int] = None,
               mode: Optional[str] = None) -> Page:
    size, style, reading = _size(a), _style(a), "rtl" if a.rtl else "ltr"
    if a.layout == "bsp":
        return page_from_bsp(number, size, panels or a.panels, mode=mode or a.mode, seed=seed,
                             snap=not a.no_snap, gutter=a.gutter, reading=reading, style=style)
    if a.layout == "preset":
        result = load_presets(a.preset_dir)
        by_name = {p.name.lower(): p for p in result.presets}
        preset = by_name.get((a.preset or "").lower())
        if preset is None:
            raise ValueError(f"no preset named {a.preset!r} in {os.path.normpath(a.preset_dir)}")
        return page_from_preset(number, size, preset, gutter=a.gutter, reading=reading, style=style)
    m = re.fullmatch(r"(\d+)x(\d+)", a.grid or "")
    if not m:
        raise ValueError("--grid should look like 3x2 (rows x columns)")
    return page_from_grid(number, size, int(m[1]), int(m[2]), _merges(a.merge),
                          gutter=a.gutter, reading=reading, style=style)


def _layout_options(p: argparse.ArgumentParser) -> None:
    lay = p.add_argument_group("layout")
    lay.add_argument("--layout", choices=("bsp", "preset", "grid"), default="bsp")
    lay.add_argument("--panels", type=int, default=5, help="bsp: number of panels (1-8)")
    lay.add_argument("--mode", choices=MODES, default="auto", help="bsp: how to cut")
    lay.add_argument("--seed", type=int, help="bsp: same seed, same layout (random if left out)")
    lay.add_argument("--no-snap", action="store_true", help="bsp: don't snap cuts to thirds and halves")
    lay.add_argument("--preset", help="preset: layout name, e.g. 'title00'")
    lay.add_argument("--preset-dir", default=DEFAULT_PRESET_DIR)
    lay.add_argument("--grid", help="grid: rows x columns, e.g. 3x2")
    lay.add_argument("--merge", action="append", default=[], help="grid: merge two neighbours, e.g. 0,0:0,1")


def next_page_number(folder: str) -> int:
    """One more than the highest page_NN.svg in a folder, so batches never overwrite."""
    if not os.path.isdir(folder):
        return 1
    numbers = [int(m[1]) for f in os.listdir(folder) if (m := PAGE_FILE.match(f))]
    return max(numbers, default=0) + 1


def _describe(page: Page) -> str:
    s, r = page.size, page.layout
    how = {"bsp": f"seed {r.get('seed')}, {r.get('mode')}", "preset": f"preset {r.get('name')}",
           "grid": f"grid {r.get('rows')}x{r.get('cols')}"}.get(r.get("kind"), "custom cells")
    return (f"{len(page.cells)} panels, {s.trim_w:g} x {s.trim_h:g} mm trim, {s.bleed:g} mm bleed, "
            f"{page.gutter:g} mm gutter, {page.reading.upper()}, {how}")


def cmd_build(a: argparse.Namespace) -> int:
    m = PAGE_FILE.match(os.path.basename(a.out))
    number = a.page or (int(m[1]) if m else 1)
    page = _build_one(a, number, a.seed)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    write_page(page, a.out)
    print(f"Wrote {a.out}: {_describe(page)}")
    if a.layout == "bsp" and len(page.cells) < a.panels:
        print(f"Note: asked for {a.panels} panels, but only {len(page.cells)} fit at this size.")
    return 0


def cmd_batch(a: argparse.Namespace) -> int:
    if not 1 <= a.count <= 50:
        raise ValueError("--count must be between 1 and 50")
    lo, hi = sorted((a.min_panels, a.max_panels))
    os.makedirs(a.folder, exist_ok=True)
    start = next_page_number(a.folder)
    rng = random.Random(a.seed)  # a batch seed makes the whole batch repeatable
    for i in range(a.count):
        if a.layout == "bsp":
            mode = rng.choice(("auto", "rows", "cols")) if a.batch_mode == "mixed" else (
                a.mode if a.batch_mode == "same" else a.batch_mode)
            seed = a.seed if a.batch_mode == "same" and a.seed is not None else rng.randrange(10_000, 100_000)
            panels = a.panels if a.batch_mode == "same" else rng.randint(lo, hi)
            page = _build_one(a, start + i, seed, panels=panels, mode=mode)
        else:
            page = _build_one(a, start + i, None)
        path = os.path.join(a.folder, page.file_name)
        write_page(page, path)
        print(f"Wrote {path}: {_describe(page)}")
    print(f"{a.count} page{'s' if a.count != 1 else ''} written, numbered from {start}.")
    return 0


def cmd_info(a: argparse.Namespace) -> int:
    doc = read_page(a.page)
    print(f"{a.page}: page {doc.page.number}")
    print(f"  {_describe(doc.page)}")
    w, h = doc.page.size.canvas_px()
    print(f"  canvas {doc.page.size.canvas_w:g} x {doc.page.size.canvas_h:g} mm = {w} x {h} px at {doc.page.size.dpi} dpi")
    if not doc.page.geometry().panels_inside_safe_area():
        print("  warning: the panel margin is smaller than the safe area, so panel edges may be trimmed")
    if doc.modified_panels:
        print(f"  panels changed in another app: {', '.join(map(str, doc.modified_panels))} "
              "(rebuilding from the hub redraws them)")
    extra = doc.foreign_elements()
    if extra:
        print(f"  {len(extra)} element{'s' if len(extra) != 1 else ''} added outside the hub (kept on save)")
    return 0


def cmd_papers(_a: argparse.Namespace) -> int:
    for name, (w, h) in PAPER_SIZES.items():
        print(f"  {name:12} {w:g} x {h:g} mm")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cpb_core", description="Build comic pages as SVG.")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build one page")
    b.add_argument("out", help="output file, e.g. page_07.svg")
    b.add_argument("--page", type=int, help="page number (default: from the file name, else 1)")
    _page_options(b); _layout_options(b)
    b.set_defaults(func=cmd_build)

    bt = sub.add_parser("batch", help="build several pages into a folder")
    bt.add_argument("folder")
    bt.add_argument("--count", type=int, default=8)
    bt.add_argument("--batch-mode", choices=("auto", "mixed", "chaos", "same"), default="auto",
                    help="bsp: how each page's layout is chosen")
    bt.add_argument("--min-panels", type=int, default=4)
    bt.add_argument("--max-panels", type=int, default=6)
    _page_options(bt); _layout_options(bt)
    bt.set_defaults(func=cmd_batch)

    i = sub.add_parser("info", help="describe a page.svg")
    i.add_argument("page")
    i.set_defaults(func=cmd_info)

    pp = sub.add_parser("papers", help="list named paper sizes")
    pp.set_defaults(func=cmd_papers)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"error: no such file: {e.filename}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
