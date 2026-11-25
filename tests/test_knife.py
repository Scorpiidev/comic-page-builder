"""Manual layouts: knife cuts at any angle, merges, insets, gutters on polygons."""

import math

import pytest

from cpb_core.build import page_from_preset, page_manual, rebuild
from cpb_core.geometry import PageSize
from cpb_core.layouts import knife
from cpb_core.layouts.cells import Cell
from cpb_core.svg import page_to_svg, parse_page

SIZE = PageSize(trim_w=170, trim_h=260, bleed=3, safe=5, margin=8, dpi=600)


def test_blank_layout_is_one_panel():
    page = page_manual(1, SIZE)
    (p,) = page.panels()
    live = page.geometry().live
    assert p.rect == live and len(p.points) == 4


def test_a_diagonal_cut_makes_two_convex_panels_a_gutter_apart():
    layout = knife.cut(knife.empty(), (0.0, 0.3), (1.0, 0.5))
    page = page_manual(1, SIZE, layout, gutter=4)
    a, b = page.panels()
    assert a.points and b.points
    assert a.rect.y < b.rect.y  # reading order: the top one first
    # Distance from the top panel's lower edge to the bottom panel's upper edge, measured square to the cut.
    live = page.geometry().live
    dx, dy = live.w, 0.2 * live.h
    n = (-dy / math.hypot(dx, dy), dx / math.hypot(dx, dy))
    top = max(x * n[0] + y * n[1] for x, y in a.points)
    bottom = min(x * n[0] + y * n[1] for x, y in b.points)
    assert bottom - top == pytest.approx(4, abs=0.01)


def test_outer_edges_stay_on_the_margins():
    layout = knife.cut(knife.empty(), (0.5, 0.0), (0.4, 1.0))
    page = page_manual(1, SIZE, layout)
    live = page.geometry().live
    xs = [x for p in page.panels() for x, _ in p.points]
    ys = [y for p in page.panels() for _, y in p.points]
    assert min(xs) == pytest.approx(live.x) and max(xs) == pytest.approx(live.right)
    assert min(ys) == pytest.approx(live.y) and max(ys) == pytest.approx(live.bottom)


def test_cuts_only_split_the_panel_they_start_in_and_merge_undoes_them():
    layout = knife.cut(knife.empty(), (0, 0.5), (1, 0.5))        # top / bottom
    layout = knife.cut(layout, (0.5, 0.6), (0.6, 1.0))             # bottom only, slanted
    assert len(knife.shapes(layout)) == 3
    segs = knife.cut_segments(layout)
    assert len(segs) == 2
    top_cut = next(path for path, *_ in segs if path == ())
    assert len(knife.shapes(knife.merge(layout, top_cut))) == 1    # merging the first cut drops the one inside it
    inner = next(path for path, *_ in segs if path != ())
    assert len(knife.shapes(knife.merge(layout, inner))) == 2


def test_missing_or_sliver_cuts_are_refused():
    with pytest.raises(ValueError):
        knife.cut(knife.empty(), (0.2, 0.2), (0.2, 0.2))
    with pytest.raises(ValueError):
        knife.cut(knife.empty(), (0.0, 0.001), (1.0, 0.0005))  # shaves off a sliver


def test_insets_sit_on_top_with_a_halo():
    layout = knife.add_inset(knife.cut(knife.empty(), (0, 0.5), (1, 0.5)), 0.55, 0.35, 0.35, 0.3)
    page = page_manual(1, SIZE, layout)
    panels = page.panels()
    assert sum(p.on_top for p in panels) == 1
    svg = page_to_svg(page)
    assert svg.index('id="cpb-halo-') < svg.index('cpb:inset="true"')
    assert parse_page(svg).page == page
    assert len(knife.shapes(knife.remove_inset(layout, 0))) == 2


def test_manual_pages_round_trip_and_reflow():
    layout = knife.cut(knife.cut(knife.empty(), (0, 0.4), (1, 0.6)), (0.3, 0.0), (0.5, 0.5))
    page = page_manual(3, SIZE, layout, gutter=3)
    svg = page_to_svg(page)
    doc = parse_page(svg)
    assert doc.page == page and doc.to_svg() == svg and not doc.modified_panels
    bigger = rebuild(page, PageSize(trim_w=210, trim_h=297, bleed=3, safe=5, margin=10, dpi=600))
    assert len(bigger.panels()) == 3 and bigger.layout == page.layout


def test_a_gutter_wider_than_a_panel_is_refused():
    layout = knife.cut(knife.empty(), (0, 0.02), (1, 0.06))
    page = page_manual(1, SIZE, layout, gutter=30)
    with pytest.raises(ValueError):
        page.panels()


def test_presets_convert_to_a_cut_tree():
    from cpb_core.layouts.presets import load_presets
    import os
    presets = load_presets(os.path.join(os.path.dirname(__file__), "..", "comicpagebuilder", "resources", "layouts")).presets
    converted = 0
    for preset in presets:
        layout = knife.from_cells(preset.cells)
        if layout is None:
            continue
        converted += 1
        rects = sorted((round(c.x, 4), round(c.y, 4), round(c.w, 4), round(c.h, 4)) for c in preset.cells)
        cut = sorted((round(s.bbox.x, 4), round(s.bbox.y, 4), round(s.bbox.w, 4), round(s.bbox.h, 4)) for s in knife.shapes(layout))
        assert cut == rects, preset.name
    assert converted >= len(presets) * 0.8


def test_pinwheel_layouts_cant_be_cut_straight_across():
    pinwheel = [Cell(0, 0, 0.6, 0.4), Cell(0.6, 0, 0.4, 0.6), Cell(0.4, 0.6, 0.6, 0.4), Cell(0, 0.4, 0.4, 0.6), Cell(0.4, 0.4, 0.2, 0.2)]
    assert knife.from_cells(pinwheel) is None
