import json
import os

import pytest

from cpb_core.layouts import close_gutters, coverage, load_presets, overlaps

PRESET_DIR = os.path.join(os.path.dirname(__file__), "..", "comicpagebuilder", "resources", "layouts")


def test_every_bundled_preset_loads():
    result = load_presets(PRESET_DIR)
    assert result.errors == []
    assert len(result.presets) == 36


def test_bundled_presets_become_perfect_tilings():
    for p in load_presets(PRESET_DIR).presets:
        assert coverage(p.cells) == pytest.approx(1.0, abs=1e-4), p.name
        assert overlaps(list(p.cells)) == [], p.name


def test_panel_count_comes_from_the_rectangles_not_the_filename():
    by_name = {p.name: p for p in load_presets(PRESET_DIR).presets}
    assert by_name["4 frames 2 rows 1"].panel_count == 5


def test_close_gutters_meets_in_the_middle():
    cells = close_gutters([{"x": 0, "y": 0, "width": 0.49, "height": 1},
                           {"x": 0.51, "y": 0, "width": 0.49, "height": 1}])
    assert cells[0].right == pytest.approx(0.5)
    assert cells[1].x == pytest.approx(0.5)


def test_broken_files_are_reported_not_hidden(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps({"layout": [{"type": "rect", "data": {"x": 0, "y": 0, "width": 1, "height": 1}}]}))
    (tmp_path / "broken.json").write_text('{"layout": [{"x": .5}]}')
    (tmp_path / "empty.json").write_text('{"layout": []}')
    result = load_presets(str(tmp_path))
    assert [p.name for p in result.presets] == ["good"]
    assert sorted(name for name, _ in result.errors) == ["broken.json", "empty.json"]
