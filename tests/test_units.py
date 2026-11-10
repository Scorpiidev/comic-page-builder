import pytest

from cpb_core.units import from_mm, mm_to_pt, mm_to_px, pt_to_mm, px_to_mm, to_mm


def test_inch_is_72_points():
    assert mm_to_pt(25.4) == pytest.approx(72.0)
    assert pt_to_mm(72.0) == pytest.approx(25.4)


def test_px_round_trip():
    assert mm_to_px(25.4, 300) == 300
    assert px_to_mm(300, 300) == pytest.approx(25.4)


@pytest.mark.parametrize("unit", ["mm", "cm", "in", "pt"])
def test_display_units_round_trip(unit):
    # The bug from 0.13: switching units must never change the stored value.
    for mm in (0.25, 3.0, 168.0, 260.0, 1000.0):
        assert to_mm(from_mm(mm, unit), unit) == pytest.approx(mm)


def test_unknown_unit_is_a_clear_error():
    with pytest.raises(ValueError, match="Unknown unit"):
        to_mm(1, "furlong")
