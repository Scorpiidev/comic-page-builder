import pytest

from cpb_core.layouts import Cell, NonRectangularMerge, coverage, grid_cells, overlaps


def test_plain_grid():
    cells = grid_cells(3, 2)
    assert len(cells) == 6 and coverage(cells) == pytest.approx(1.0)


def test_merging_a_row_makes_a_wide_panel():
    cells = grid_cells(3, 2, [((0, 0), (0, 1))])
    assert Cell(0, 0, 1, 1 / 3) in cells and len(cells) == 5
    assert overlaps(cells) == []


def test_l_shape_is_refused_with_the_cells_named():
    with pytest.raises(NonRectangularMerge) as e:
        grid_cells(2, 2, [((0, 0), (0, 1)), ((0, 0), (1, 0))])
    assert e.value.group == [(0, 0), (0, 1), (1, 0)]


def test_merge_must_be_between_neighbours():
    with pytest.raises(ValueError, match="neighbours"):
        grid_cells(3, 3, [((0, 0), (2, 2))])
