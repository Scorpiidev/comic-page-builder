import os

from cpb_core.cli import main, next_page_number
from cpb_core.svg import read_page


def test_build_takes_the_page_number_from_the_file_name(tmp_path, capsys):
    out = tmp_path / "page_07.svg"
    assert main(["build", str(out), "--panels", "6", "--seed", "48213"]) == 0
    page = read_page(str(out)).page
    assert page.number == 7 and len(page.cells) == 6 and page.layout["seed"] == 48213
    assert "6 panels" in capsys.readouterr().out


def test_build_preset_and_grid(tmp_path):
    assert main(["build", str(tmp_path / "cover.svg"), "--layout", "preset", "--preset", "title00"]) == 0
    assert read_page(str(tmp_path / "cover.svg")).page.layout == {"kind": "preset", "name": "title00"}
    assert main(["build", str(tmp_path / "g.svg"), "--layout", "grid", "--grid", "3x2", "--merge", "0,0:0,1", "--rtl"]) == 0
    assert len(read_page(str(tmp_path / "g.svg")).page.cells) == 5


def test_small_pages_say_how_many_panels_fit(tmp_path, capsys):
    main(["build", str(tmp_path / "p.svg"), "--paper", "postcard", "--panels", "8", "--seed", "1"])
    assert "only" in capsys.readouterr().out


def test_batch_continues_numbering_and_never_overwrites(tmp_path):
    folder = tmp_path / "Pages"
    assert main(["batch", str(folder), "--count", "3", "--seed", "7"]) == 0
    first = (folder / "page_02.svg").read_text()
    assert main(["batch", str(folder), "--count", "2", "--seed", "8", "--batch-mode", "mixed"]) == 0
    assert sorted(os.listdir(folder)) == [f"page_0{i}.svg" for i in range(1, 6)]
    assert (folder / "page_02.svg").read_text() == first
    assert next_page_number(str(folder)) == 6


def test_same_batch_seed_gives_the_same_pages(tmp_path):
    main(["batch", str(tmp_path / "a"), "--count", "4", "--seed", "99"])
    main(["batch", str(tmp_path / "b"), "--count", "4", "--seed", "99"])
    for i in range(1, 5):
        assert (tmp_path / "a" / f"page_0{i}.svg").read_text() == (tmp_path / "b" / f"page_0{i}.svg").read_text()


def test_info_and_errors(tmp_path, capsys):
    out = tmp_path / "page_01.svg"
    main(["build", str(out), "--seed", "5", "--margin", "3"])
    assert main(["info", str(out)]) == 0
    text = capsys.readouterr().out
    assert "4110 x 6283 px" in text and "safe area" in text
    assert main(["build", str(tmp_path / "x.svg"), "--paper", "Tabloid"]) == 1
    assert "Unknown paper size" in capsys.readouterr().err
    assert main(["build", str(tmp_path / "x.svg"), "--layout", "grid", "--grid", "2x2",
                 "--merge", "0,0:0,1", "--merge", "0,0:1,0"]) == 1
    assert "don't form a rectangle" in capsys.readouterr().err
