import json
import xml.etree.ElementTree as ET

import pytest

from cpb_core.build import page_from_bsp
from cpb_core.geometry import PageSize
from cpb_core.project import create_project, load_project, update_settings
from cpb_core.svg.ns import SVG, q


def test_create_makes_the_folders_and_manifest(tmp_path):
    p = create_project(str(tmp_path / "MyComic"), "My Comic", folders=("script", "reference"))
    assert sorted(x.name for x in (tmp_path / "MyComic").iterdir()) == ["pages", "project.json", "reference", "script"]
    data = json.loads((tmp_path / "MyComic" / "project.json").read_text())
    assert data["format"] == "cpb-project" and data["name"] == "My Comic"
    assert p.folders == ("pages", "script", "reference")  # pages is always there


def test_create_never_overwrites_an_existing_project(tmp_path):
    create_project(str(tmp_path), "First")
    with pytest.raises(ValueError, match="already has a project"):
        create_project(str(tmp_path), "Second")


def test_blank_pages_and_round_trip(tmp_path):
    p = create_project(str(tmp_path), "Zine", reading="rtl", size=PageSize(148, 210), blank_pages=3, seed=1)
    assert [e.number for e in p.pages] == [1, 2, 3]
    assert (tmp_path / "pages" / "002" / "page.svg").exists()
    again = load_project(str(tmp_path))
    assert again == p
    assert again.load_page(2).reading == "rtl"
    assert again.load_page(2).size.trim_w == 148


def test_batch_continues_numbering(tmp_path):
    p = create_project(str(tmp_path), "C", blank_pages=2, seed=2)
    made = p.add_batch(3, mode="mixed", seed=9)
    assert [x.number for x in made] == [3, 4, 5]
    assert [e.number for e in load_project(str(tmp_path)).pages] == [1, 2, 3, 4, 5]


def test_batch_same_as_copies_a_layout(tmp_path):
    p = create_project(str(tmp_path), "C")
    first = p.new_page(6, seed=48213)
    copies = p.add_batch(2, mode="same", same_as=first.number)
    assert all(c.cells == first.cells for c in copies)


def test_status_changes_are_saved(tmp_path):
    p = create_project(str(tmp_path), "C", blank_pages=1, seed=3)
    p.set_status(1, "inks")
    assert load_project(str(tmp_path)).entry(1).status == "inks"
    with pytest.raises(ValueError, match="status must be"):
        p.set_status(1, "sleeping")


def test_saving_a_page_keeps_what_other_apps_added(tmp_path):
    p = create_project(str(tmp_path), "C")
    page = p.new_page(4, seed=5)
    path = p.page_path(page.number)
    root = ET.parse(path).getroot()
    ET.SubElement(root, q(SVG, "g"), {"id": "my-ink-layer"})
    ET.ElementTree(root).write(path, encoding="unicode")
    p.save_page(page_from_bsp(page.number, p.size, 5, seed=6))  # rebuild from the hub
    text = open(path, encoding="utf-8").read()
    assert 'id="my-ink-layer"' in text and text.count('id="cpb-panel-') == 5


def test_settings_change_defaults_not_existing_pages(tmp_path):
    p = create_project(str(tmp_path), "C", blank_pages=1, seed=4)
    p2 = update_settings(p, name="Renamed", size=PageSize(210, 297), folders=("pages", "exports"))
    assert load_project(str(tmp_path)).name == "Renamed"
    assert (tmp_path / "exports").is_dir()
    assert p2.load_page(1).size.trim_w == 168  # the old page keeps its size
    assert p2.new_page(4, seed=1).size.trim_w == 210


@pytest.mark.parametrize("content, msg", [
    (None, "isn't a comic project"),
    ("{broken", "damaged"),
    ('{"format": "something-else"}', "isn't a Comic Page Builder project"),
    ('{"format": "cpb-project", "version": 99}', "newer version"),
])
def test_bad_folders_explain_themselves(tmp_path, content, msg):
    if content is not None:
        (tmp_path / "project.json").write_text(content)
    with pytest.raises(ValueError, match=msg):
        load_project(str(tmp_path))
