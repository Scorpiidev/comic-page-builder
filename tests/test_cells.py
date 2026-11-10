import pytest

from cpb_core.geometry import Rect
from cpb_core.layouts import Cell, apply_gutter, reading_order


def two_by_two():
    return [Cell(0.5, 0.5, 0.5, 0.5), Cell(0, 0, 0.5, 0.5), Cell(0.5, 0, 0.5, 0.5), Cell(0, 0.5, 0.5, 0.5)]


def test_reading_order_ltr():
    order = reading_order(two_by_two())
    assert [(c.x, c.y) for c in order] == [(0, 0), (0.5, 0), (0, 0.5), (0.5, 0.5)]


def test_reading_order_rtl_for_manga():
    order = reading_order(two_by_two(), "rtl")
    assert [(c.x, c.y) for c in order] == [(0.5, 0), (0, 0), (0.5, 0.5), (0, 0.5)]


def test_tall_panel_reads_with_the_row_it_starts_in():
    cells = [Cell(0.5, 0.5, 0.5, 0.5), Cell(0, 0, 0.5, 1), Cell(0.5, 0, 0.5, 0.5)]
    order = reading_order(cells)
    assert order == [Cell(0, 0, 0.5, 1), Cell(0.5, 0, 0.5, 0.5), Cell(0.5, 0.5, 0.5, 0.5)]


def test_gutter_is_exact_between_neighbours_and_absent_at_the_border():
    live = Rect(10, 10, 100, 200)
    left, right = apply_gutter([Cell(0, 0, 0.5, 1), Cell(0.5, 0, 0.5, 1)], live, gutter_mm=4)
    assert right.x - left.right == pytest.approx(4)
    assert left.x == 10 and right.right == pytest.approx(110)
    assert left.y == 10 and left.bottom == pytest.approx(210)


def test_changing_the_gutter_keeps_the_layout_shape():
    live = Rect(0, 0, 100, 100)
    cells = [Cell(0, 0, 1 / 3, 1), Cell(1 / 3, 0, 2 / 3, 1)]
    for g in (0, 3, 8):
        a, b = apply_gutter(cells, live, g)
        assert (a.right + b.x) / 2 == pytest.approx(100 / 3)  # cut stays in place


def test_gutter_wider_than_panel_is_an_error():
    with pytest.raises(ValueError, match="wider than a panel"):
        apply_gutter([Cell(0, 0, 0.02, 1), Cell(0.02, 0, 0.98, 1)], Rect(0, 0, 100, 100), 10)
