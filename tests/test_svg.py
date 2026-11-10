"""page.svg writer and reader: golden files, round trips, and edits made in other apps."""

import os
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

from cpb_core.build import page_from_bsp, page_from_grid, page_from_preset, rebuild
from cpb_core.geometry import PageSize
from cpb_core.layouts import load_presets
from cpb_core.model import PanelStyle
from cpb_core.svg import page_to_svg, parse_page, read_page
from cpb_core.svg.ns import CPB, SVG, q

HERE = os.path.dirname(__file__)
GOLDEN = os.path.join(HERE, "golden")
PRESETS = os.path.join(HERE, "..", "comicpagebuilder", "resources", "layouts")
US = PageSize(trim_w=168, trim_h=260)


def golden_pages():
    title00 = next(p for p in load_presets(PRESETS).presets if p.name == "title00")
    return {
        "bsp_us_comic_seed48213.svg": page_from_bsp(7, US, 6, seed=48213),
        "preset_title00_rounded.svg": page_from_preset(1, US, title00, style=PanelStyle(corner_radius=1.5, stroke="#3d1f2e")),
        "grid_3x2_rtl_a5.svg": page_from_grid(12, PageSize(148, 210, bleed=5, margin=6), 3, 2, [((0, 0), (0, 1))], reading="rtl", gutter=4),
    }


@pytest.mark.parametrize("filename", sorted(golden_pages()))
def test_golden_files(filename):
    """The writer's output is stable. Regenerate on purpose with CPB_UPDATE_GOLDEN=1."""
    text = page_to_svg(golden_pages()[filename])
    path = os.path.join(GOLDEN, filename)
    if os.environ.get("CPB_UPDATE_GOLDEN") == "1":
        os.makedirs(GOLDEN, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    with open(path, encoding="utf-8") as f:
        assert text == f.read(), f"{filename} changed; if that's intended, rerun with CPB_UPDATE_GOLDEN=1"


@pytest.mark.parametrize("filename", sorted(golden_pages()))
def test_golden_files_read_back_to_the_same_page(filename):
    original = golden_pages()[filename]
    doc = read_page(os.path.join(GOLDEN, filename))
    assert doc.page == original
    assert doc.modified_panels == []
    assert doc.foreign_elements() == []


def test_round_trip_on_many_random_pages():
    for seed in range(150):
        for mode in ("auto", "rows", "cols", "chaos"):
            page = page_from_bsp(1 + seed % 30, US, 1 + seed % 8, mode=mode, seed=seed,
                                 reading="rtl" if seed % 3 == 0 else "ltr", gutter=seed % 6)
            text = page_to_svg(page)
            doc = parse_page(text)
            assert doc.page == page
            assert doc.to_svg() == text  # writing again changes nothing


def test_file_structure():
    root = ET.fromstring(page_to_svg(page_from_bsp(7, US, 4, seed=3)))
    assert root.get("width") == "174mm" and root.get("viewBox") == "0 0 174 266"
    layers = [el.get("id") for el in root if el.tag == q(SVG, "g")]
    assert layers == ["cpb-paper", "cpb-panels", "cpb-letters", "cpb-guides"]  # bottom to top
    panels = [el for el in root.iter(q(SVG, "path")) if el.get("id", "").startswith("cpb-panel-")]
    assert [el.get(q(CPB, "index")) for el in panels] == ["1", "2", "3", "4"]
    clips = [el.get("id") for el in root.iter(q(SVG, "clipPath"))]
    assert clips == ["cpb-clip-1", "cpb-clip-2", "cpb-clip-3", "cpb-clip-4"]
    guides = next(el for el in root if el.get("id") == "cpb-guides")
    assert guides.get(q(CPB, "print")) == "false"


def test_things_added_in_other_apps_survive_a_rebuild():
    text = page_to_svg(page_from_bsp(7, US, 5, seed=11))
    root = ET.fromstring(text)
    # Simulate edits from Illustrator/Inkscape: a new layer, a doodle inside
    # the Panels layer, a balloon placeholder in Letters, and a comment.
    sketch = ET.SubElement(root, q(SVG, "g"), {"id": "my-sketch"})
    ET.SubElement(sketch, q(SVG, "circle"), {"cx": "50", "cy": "50", "r": "10"})
    panels = next(el for el in root if el.get("id") == "cpb-panels")
    ET.SubElement(panels, q(SVG, "path"), {"id": "speed-lines", "d": "M0 0L10 10"})
    letters = next(el for el in root if el.get("id") == "cpb-letters")
    ET.SubElement(letters, q(SVG, "text"), {"x": "20", "y": "20"}).text = "HELLO!"
    root.insert(0, ET.Comment(" note from the artist "))
    edited = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    doc = parse_page(edited)
    assert len(doc.foreign_elements()) == 5  # comment, layer, circle, speed lines, text
    wider = replace(doc.page, gutter=6.0)
    out = doc.to_svg(wider)

    again = parse_page(out)
    assert again.page.gutter == 6.0
    ids = {el.get("id") for el in again.root.iter()}
    assert {"my-sketch", "speed-lines"} <= ids
    assert "HELLO!" in out and "note from the artist" in out
    assert len(again.foreign_elements()) == 5


def test_panels_reshaped_in_another_app_are_reported():
    root = ET.fromstring(page_to_svg(page_from_bsp(7, US, 4, seed=3)))
    p2 = next(el for el in root.iter() if el.get("id") == "cpb-panel-2")
    p2.set("d", "M10 10L90 10L60 80Z")  # someone drew a diagonal panel
    doc = parse_page(ET.tostring(root, encoding="unicode"))
    assert doc.modified_panels == [2]


def test_rebuild_on_a_new_size_keeps_the_layout_character():
    page = page_from_bsp(3, US, 6, seed=48213)
    bigger = rebuild(page, PageSize(210, 297))
    assert bigger.layout == page.layout
    assert len(bigger.cells) == 6


@pytest.mark.parametrize("text, msg", [
    ("not xml at all <", "valid SVG/XML"),
    ('<svg xmlns="http://www.w3.org/2000/svg"/>', "wasn't made by Comic Page Builder"),
    ('<html/>', "isn't an SVG"),
    (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:cpb="{CPB}" cpb:format="cpb-page" cpb:version="9"/>', "newer version"),
])
def test_bad_files_explain_themselves(text, msg):
    with pytest.raises(ValueError, match=msg):
        parse_page(text)
