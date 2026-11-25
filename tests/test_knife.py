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
    top_cut = next(where for where, *_ in segs if where == (-1, ()))
    assert len(knife.shapes(knife.merge(layout, top_cut))) == 1    # merging the first cut drops the one inside it
    inner = next(where for where, *_ in segs if where != (-1, ()))
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
    assert sum(p.on_top for p in panels) == 1 and panels[-1].on_top is not None
    svg = page_to_svg(page)
    assert svg.index('id="cpb-inset-gap-1"') < svg.index('cpb:inset="1"')
    assert parse_page(svg).page == page
    assert len(knife.shapes(knife.remove_inset(layout, 0))) == 2
    no_gap = page_manual(1, SIZE, dict(layout, inset_gap=False))
    assert "cpb-inset-gap" not in page_to_svg(no_gap)


def test_insets_can_be_cut_and_their_cuts_move_with_them():
    layout = knife.add_inset(knife.empty(), 0.5, 0.5, 0.4, 0.4)
    layout = knife.cut(layout, (0.7, 0.45), (0.7, 0.95))      # over the inset: cuts the inset, not the page
    assert [s.inset for s in knife.shapes(layout)] == [-1, 0, 0]
    page = page_manual(1, SIZE, layout, gutter=4)
    a, b = [p for p in page.panels() if p.on_top]
    assert b.rect.x - a.rect.right == pytest.approx(4, abs=0.01)
    moved = knife.set_inset_rect(layout, 0, 0.1, 0.1, 0.4, 0.4)
    xs = sorted(s.bbox.x for s in knife.shapes(moved) if s.inset == 0)
    assert xs == pytest.approx([0.1, 0.3])                      # the cut is still in the middle of the inset
    (where, *_), = [seg for seg in knife.cut_segments(layout) if seg[0][0] == 0]
    assert len(knife.shapes(knife.merge(layout, where))) == 2


def test_sliding_a_cut_keeps_its_angle():
    layout = knife.cut(knife.empty(), (0.0, 0.3), (1.0, 0.5))
    slid = knife.slide(layout, (-1, ()), 0.0, 0.1)
    x1, y1, x2, y2 = slid["tree"]["cut"]
    assert (y2 - y1) / (x2 - x1) == pytest.approx(0.2)          # same slope
    assert knife.cut_segments(slid)[0][1][1] > knife.cut_segments(layout)[0][1][1]
    with pytest.raises(ValueError):
        knife.slide(layout, (-1, ()), 0.0, 0.9)                 # would push the bottom panel off the page


def test_a_cut_near_a_corner_never_pokes_outside_the_panel():
    # Ivón's screenshot: a diagonal that just misses an inset's corner drew past it.
    layout = knife.add_inset(knife.empty(), 0.3, 0.5, 0.5, 0.3)
    layout = knife.cut(layout, (0.299, 0.505), (0.8, 0.8))
    page = page_manual(1, SIZE, layout, gutter=3)
    live = page.geometry().live
    x0, y0 = live.x + 0.3 * live.w, live.y + 0.5 * live.h
    for p in page.panels():
        if p.on_top:
            for x, y in p.points:
                assert x0 - 1e-6 <= x <= x0 + 0.5 * live.w + 1e-6 and y0 - 1e-6 <= y <= y0 + 0.3 * live.h + 1e-6


def test_hand_cut_panels_get_rounded_corners():
    from cpb_core.svg.writer import polygon_path
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert "C" not in polygon_path(square, 0)
    d = polygon_path(square, 2)
    assert d.count("C") == 4 and "M2 0" in d.replace(",", " ") or d.startswith("M")
    sharp = polygon_path([(0, 0), (10, 0), (0, 1)], 50)   # a huge radius is capped by the short edges
    assert sharp.count("C") == 3


def test_centred_cut_splits_the_panel_in_half():
    (p1, p2) = knife.centred(knife.SQUARE, (0.1, 0.2), (0.9, 0.2))
    assert p1[1] == pytest.approx(0.5) and p2[1] == pytest.approx(0.5)


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
