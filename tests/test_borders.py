"""The borders-only SVG for Clip Studio Paint (see importers/M2_RESULTS.md)."""

import xml.etree.ElementTree as ET

import pytest

from cpb_core.build import page_from_bsp
from cpb_core.cli import main
from cpb_core.geometry import PageSize
from cpb_core.model import PanelStyle
from cpb_core.svg import borders_file_name, borders_svg, page_to_svg, parse_page
from cpb_core.svg.ns import CPB, SVG, q

US = PageSize(trim_w=168, trim_h=260)


def _root(text):
    return ET.fromstring(text.split("\n", 1)[1])  # skip the XML declaration


def test_only_panel_outlines_go_in():
    # CSP puts everything in the file on one layer, so paper, guides, clips and fills must stay out.
    page = page_from_bsp(7, US, 6, seed=48213, style=PanelStyle(fill="#fff4f8"))
    root = _root(borders_svg(page))
    kids = list(root)
    assert [el.tag for el in kids] == [q(SVG, "path")] * 6
    assert [el.get("id") for el in kids] == [f"cpb-border-{i}" for i in range(1, 7)]
    for el in kids:
        assert el.get("fill") == "none"
        assert el.get("stroke") == "#1b1b1b" and el.get("stroke-width") == "0.6"
    assert root.get(q(CPB, "format")) == "cpb-borders"


@pytest.mark.parametrize("radius", [0.0, 2.5])
def test_lines_up_with_page_svg(radius):
    # Same canvas and the very same path data, so the lines land on the PSD's frames.
    page = page_from_bsp(3, US, 5, seed=11, style=PanelStyle(corner_radius=radius))
    page_root, border_root = _root(page_to_svg(page)), _root(borders_svg(page))
    for attr in ("width", "height", "viewBox"):
        assert border_root.get(attr) == page_root.get(attr)
    panels = {el.get("id")[len("cpb-panel-"):]: el.get("d") for el in page_root.iter()
              if el.get("id", "").startswith("cpb-panel-")}
    borders = {el.get("id")[len("cpb-border-"):]: el.get("d") for el in border_root}
    assert borders == panels


def test_no_border_means_nothing_to_export():
    page = page_from_bsp(1, US, 3, seed=1, style=PanelStyle(stroke_width=0))
    with pytest.raises(ValueError, match="no border"):
        borders_svg(page)


def test_the_reader_refuses_a_borders_file():
    with pytest.raises(ValueError, match="borders-only export"):
        parse_page(borders_svg(page_from_bsp(1, US, 3, seed=1)))


def test_file_name_sits_next_to_the_page():
    assert borders_file_name("pages/007/page_07.svg") == "pages/007/page_07_borders.svg"


def test_cli_writes_the_borders_next_to_the_page(tmp_path, capsys):
    page = tmp_path / "page_07.svg"
    main(["build", str(page), "--panels", "6", "--seed", "48213"])
    assert main(["borders", str(page)]) == 0
    out = tmp_path / "page_07_borders.svg"
    assert len(list(_root(out.read_text(encoding="utf-8")))) == 6
    assert "Import > Vector" in capsys.readouterr().out
    assert main(["borders", str(page), "-o", str(tmp_path / "b.svg")]) == 0
    assert (tmp_path / "b.svg").exists()
    assert main(["borders", str(out)]) == 1
    assert "borders-only export" in capsys.readouterr().err
