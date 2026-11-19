import pytest

from cpb_core.lettering import LetteringPreset, cap_height_mm, recommend_pt, verdict, working_pt
from cpb_core.project import create_project, load_project, set_lettering_preset


def test_cap_height_of_a_typical_comic_font():
    # 8.5 pt with caps at 0.70 of the em prints about 2.1 mm tall (the prototype's example).
    assert cap_height_mm(8.5, 0.70) == pytest.approx(2.099, abs=0.01)


def test_recommendation_hits_the_target_and_rounds_to_half_points():
    assert recommend_pt(0.70, "dialogue") == 8.5
    assert recommend_pt(0.62, "dialogue") == 9.5  # shorter caps need a bigger size
    assert recommend_pt(0.70, "sfx") > recommend_pt(0.70, "dialogue")


def test_working_size_follows_the_drawing_scale():
    assert working_pt(8.5, 2) == 17


@pytest.mark.parametrize("cap, kind", [(1.3, "bad"), (1.8, "small"), (2.1, "good")])
def test_verdicts(cap, kind):
    assert verdict(cap, "dialogue")[0] == kind


def test_bad_inputs_explain_themselves():
    with pytest.raises(ValueError, match="role"):
        recommend_pt(0.7, "shouting")
    with pytest.raises(ValueError, match="ratio"):
        recommend_pt(7, "dialogue")


def test_presets_are_saved_in_the_project(tmp_path):
    p = create_project(str(tmp_path), "C")
    set_lettering_preset(p, "dialogue", LetteringPreset("Comic Neue", "Bold", 8.5, 0.7))
    again = load_project(str(tmp_path))
    assert again.lettering["dialogue"] == LetteringPreset("Comic Neue", "Bold", 8.5, 0.7)
    assert again.lettering["dialogue"].cap_mm == pytest.approx(2.1, abs=0.01)
    with pytest.raises(ValueError):
        set_lettering_preset(p, "narration", LetteringPreset("X", "Regular", 8, 0.7))


# ---------- font files ----------
import os
import struct
import xml.etree.ElementTree as ET

from cpb_core.lettering import FontChoice, build_sheet, read_font_file, scan_fonts, sheet_svg, sizes_around


def _name_table(names: dict[int, str]) -> bytes:
    """A 'name' table with Windows (platform 3) UTF-16 records, like real fonts."""
    records, strings = b"", b""
    for name_id, text in sorted(names.items()):
        raw = text.encode("utf-16-be")
        records += struct.pack(">6H", 3, 1, 0x409, name_id, len(raw), len(strings))
        strings += raw
    return struct.pack(">3H", 0, len(names), 6 + 12 * len(names)) + records + strings


def _os2_table(version: int, cap: int, x_height: int, weight: int = 700, italic: bool = False) -> bytes:
    t = bytearray(96)
    struct.pack_into(">H", t, 0, version)
    struct.pack_into(">H", t, 4, weight)
    struct.pack_into(">H", t, 62, 1 if italic else 0)
    struct.pack_into(">h", t, 86, x_height)
    struct.pack_into(">h", t, 88, cap)
    return bytes(t if version >= 2 else t[:78])


def make_font(family="Test Comic", style="Bold", ps="TestComic-Bold", upem=1000, cap=700, os2_version=4) -> bytes:
    """A minimal sfnt: just the head, name and OS/2 tables the reader looks at."""
    head = bytearray(54)
    struct.pack_into(">H", head, 18, upem)
    tables = {"OS/2": _os2_table(os2_version, cap, 500), "head": bytes(head),
              "name": _name_table({1: family, 2: style, 4: f"{family} {style}", 6: ps})}
    out = struct.pack(">4sHHHH", b"\x00\x01\x00\x00", len(tables), 0, 0, 0)
    offset = 12 + 16 * len(tables)
    body = b""
    for tag, data in tables.items():
        out += struct.pack(">4sIII", tag.encode("latin-1"), 0, offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return out + body


def test_reads_names_and_cap_height(tmp_path):
    path = tmp_path / "TestComic-Bold.ttf"
    path.write_bytes(make_font(upem=2048, cap=1434))
    [fi] = read_font_file(str(path))
    assert (fi.family, fi.style, fi.ps_name) == ("Test Comic", "Bold", "TestComic-Bold")
    assert fi.cap_ratio == pytest.approx(1434 / 2048)
    assert fi.weight == 700


def test_old_os2_tables_have_no_cap_height(tmp_path):
    path = tmp_path / "old.ttf"
    path.write_bytes(make_font(os2_version=1))
    assert read_font_file(str(path))[0].cap_ratio is None  # the hub then asks Qt


def test_collections_list_every_face(tmp_path):
    a, b = make_font(style="Regular", ps="T-Regular"), make_font(style="Bold", ps="T-Bold")
    start = 12 + 8
    blob = bytearray(struct.pack(">4sII", b"ttcf", 0x00010000, 2) + struct.pack(">II", start, start + len(a)))
    # Each face's table offsets are relative to the file, so shift them.
    def shifted(font: bytes, base: int) -> bytes:
        f = bytearray(font)
        n = struct.unpack_from(">H", f, 4)[0]
        for i in range(n):
            o = 12 + 16 * i + 8
            struct.pack_into(">I", f, o, struct.unpack_from(">I", f, o)[0] + base)
        return bytes(f)
    blob += shifted(a, start) + shifted(b, start + len(a))
    path = tmp_path / "pair.ttc"
    path.write_bytes(bytes(blob))
    assert [fi.style for fi in read_font_file(str(path))] == ["Regular", "Bold"]


def test_scan_reports_broken_files_and_uses_the_cache(tmp_path):
    (tmp_path / "good.ttf").write_bytes(make_font())
    (tmp_path / "broken.otf").write_bytes(b"not a font at all")
    cache = tmp_path / "cache" / "fonts.json"
    first = scan_fonts([(str(tmp_path), True)], cache_path=str(cache))
    assert [f.family for f in first.fonts] == ["Test Comic"] and first.fonts[0].user_installed
    assert [os.path.basename(p) for p, _ in first.errors] == ["broken.otf"]
    second = scan_fonts([(str(tmp_path), True)], cache_path=str(cache))
    assert second.fonts == first.fonts


@pytest.mark.skipif(not os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), reason="no DejaVu here")
def test_a_real_font_without_cap_height():
    # DejaVu Sans has a version 1 OS/2 table, so the file doesn't say; the hub measures it with Qt instead.
    [fi] = read_font_file("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    assert (fi.family, fi.style, fi.ps_name) == ("DejaVu Sans", "Book", "DejaVuSans")
    assert fi.cap_ratio is None


# ---------- calibration sheet ----------
NEUE = FontChoice("Comic Neue", "Bold", 0.70, "ComicNeue-Bold")


def test_sizes_go_around_the_recommendation():
    assert sizes_around(8.5) == [7.0, 7.5, 8.0, 8.5, 9.0, 9.5]
    assert sizes_around(4.5)[0] == 4.0  # never below the minimum


def test_sheet_layout_codes_and_fit():
    sheet = build_sheet([NEUE, FontChoice("Kalam", "Bold", 0.62)], paper="A4")
    assert [s.code for s in sheet.samples][:3] == ["A1", "A2", "A3"]
    assert sheet.sample("b4").font.family == "Kalam"
    assert sheet.sample("A4").size_pt == 8.5
    for s in sheet.samples:
        assert s.x >= 15 and s.x + s.w <= 210 - 15 + 1e-6 and s.y + s.h <= 297 - 15
    assert sheet.ruler[2] == 100


def test_sheet_limits_explain_themselves():
    with pytest.raises(ValueError, match="fits 3 fonts"):
        build_sheet([NEUE] * 4)
    with pytest.raises(ValueError, match="at least one"):
        build_sheet([])
    with pytest.raises(ValueError, match="paper"):
        build_sheet([NEUE], paper="Tabloid")


def test_sheet_svg_is_real_size_and_valid():
    root = ET.fromstring(sheet_svg(build_sheet([NEUE], title="My Comic")))
    assert root.get("width") == "210mm" and root.get("height") == "297mm"
    assert "A6 · 9.5 pt" in sheet_svg(build_sheet([NEUE]))


def test_presets_keep_the_postscript_name(tmp_path):
    p = create_project(str(tmp_path), "C")
    set_lettering_preset(p, "whisper", LetteringPreset("Comic Neue", "Bold", 7.0, 0.7, "ComicNeue-Bold"))
    assert load_project(str(tmp_path)).lettering["whisper"].ps_name == "ComicNeue-Bold"
