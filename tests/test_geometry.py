import pytest

from cpb_core.geometry import PageGeometry, PageSize, Rect


def us_comic(**kw):
    return PageSize(trim_w=168, trim_h=260, **kw)


def test_canvas_is_always_trim_plus_two_bleeds():
    s = us_comic(bleed=3)
    assert (s.canvas_w, s.canvas_h) == (174, 266)
    # Changing bleed changes the canvas: they can't drift apart (0.13 bug).
    s2 = us_comic(bleed=5)
    assert (s2.canvas_w, s2.canvas_h) == (178, 270)


def test_canvas_pixels():
    assert us_comic(bleed=3, dpi=600).canvas_px() == (4110, 6283)


def test_geometry_rects():
    g = PageGeometry.of(us_comic(bleed=3, safe=5, margin=8))
    assert g.canvas == Rect(0, 0, 174, 266)
    assert g.trim == Rect(3, 3, 168, 260)
    assert g.safe == Rect(8, 8, 158, 250)
    assert g.live == Rect(11, 11, 152, 244)
    assert g.panels_inside_safe_area()


def test_margin_smaller_than_safe_area_is_detected():
    g = PageGeometry.of(us_comic(safe=5, margin=3))
    assert not g.panels_inside_safe_area()


def test_safe_area_is_independent_of_bleed():
    a = PageGeometry.of(us_comic(bleed=3, safe=5))
    b = PageGeometry.of(us_comic(bleed=10, safe=5))
    assert a.safe.w == b.safe.w and a.safe.h == b.safe.h


def test_orientation_swaps_trim():
    s = us_comic()
    assert s.landscape().trim_w == 260 and s.landscape().trim_h == 168
    assert s.portrait() is s


@pytest.mark.parametrize("kw, msg", [
    (dict(trim_w=0, trim_h=260), "positive"),
    (dict(trim_w=168, trim_h=260, margin=90), "no room for panels"),
    (dict(trim_w=168, trim_h=260, bleed=-1), "can't be negative"),
    (dict(trim_w=168, trim_h=260, dpi=10), "between 72 and 2400"),
])
def test_invalid_sizes_explain_themselves(kw, msg):
    with pytest.raises(ValueError, match=msg):
        PageSize(**kw)
