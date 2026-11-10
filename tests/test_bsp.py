import itertools

import pytest

from cpb_core.layouts import MODES, coverage, generate, overlaps

LIVE_A4 = (194, 281)       # A4 trim minus 8 mm margins
LIVE_US = (152, 244)       # US Comic trim minus 8 mm margins
LIVE_POSTCARD = (84, 132)  # 100 x 148 postcard minus 8 mm margins


def test_same_seed_same_layout():
    a = generate(6, *LIVE_US, seed=48213)
    b = generate(6, *LIVE_US, seed=48213)
    assert a == b


def test_different_seeds_usually_differ():
    layouts = {tuple(generate(5, *LIVE_US, mode="chaos", seed=s, snap=False)) for s in range(20)}
    assert len(layouts) > 10


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("snap", [True, False])
def test_cells_always_tile_the_live_area(mode, snap):
    for n, seed in itertools.product(range(1, 9), range(40)):
        cells = generate(n, *LIVE_A4, mode=mode, seed=seed, snap=snap)
        assert coverage(cells) == pytest.approx(1.0)
        assert overlaps(cells) == []
        assert all(0 <= c.x and c.right <= 1 + 1e-9 and 0 <= c.y and c.bottom <= 1 + 1e-9 for c in cells)


@pytest.mark.parametrize("mode", MODES)
def test_big_pages_always_get_the_panels_asked_for(mode):
    # 0.13 bug: averaging the gutters made the generator silently give up.
    for live in (LIVE_A4, LIVE_US):
        for n, seed in itertools.product(range(1, 9), range(200)):
            assert len(generate(n, *live, mode=mode, seed=seed)) == n


def test_minimum_panel_size_is_respected_in_mm():
    for seed in range(200):
        for c in generate(8, *LIVE_POSTCARD, mode="chaos", seed=seed, snap=False):
            assert c.w * LIVE_POSTCARD[0] >= 30 - 1e-6
            assert c.h * LIVE_POSTCARD[1] >= 40 - 1e-6


def test_small_pages_return_fewer_panels_instead_of_tiny_ones():
    cells = generate(8, *LIVE_POSTCARD, seed=1)
    assert 1 <= len(cells) < 8


def test_rows_mode_makes_full_width_strips():
    cells = generate(4, *LIVE_US, mode="rows", seed=3)
    assert all(c.w == pytest.approx(1.0) for c in cells)


def test_bad_mode_is_rejected():
    with pytest.raises(ValueError):
        generate(3, *LIVE_US, mode="diagonal")
