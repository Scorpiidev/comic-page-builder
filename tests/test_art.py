"""Drawn pages (D7): image headers, page size from the art, the Art layer."""

import struct
import zlib

import pytest

from cpb_core.art import art_size, image_info
from cpb_core.project import create_project, load_project
from cpb_core.svg import page_to_svg, parse_page
from cpb_core.units import MM_PER_INCH


def png(path, w, h, dpi=None):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    body = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    if dpi:
        ppm = round(dpi / 0.0254)
        body += chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
    raw = b"".join(b"\0" + b"\xff" * w for _ in range(h))
    body += chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + body)
    return str(path)


def jpeg(path, w, h, dpi=None):
    app0 = b"JFIF\0" + bytes([1, 1, 1 if dpi else 0]) + struct.pack(">HH", dpi or 1, dpi or 1) + b"\0\0"
    sof = bytes([8]) + struct.pack(">HH", h, w) + bytes([1, 1, 0x11, 0])
    data = (b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", len(app0) + 2) + app0
            + b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9")
    path.write_bytes(data)
    return str(path)


def webp(path, w, h):
    vp8x = bytes(4) + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
    chunk = b"VP8X" + struct.pack("<I", len(vp8x)) + vp8x
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk)
    return str(path)


def test_reads_size_and_resolution_from_headers(tmp_path):
    assert image_info(png(tmp_path / "a.png", 30, 20, dpi=300)) == image_info(png(tmp_path / "b.png", 30, 20, dpi=300))
    i = image_info(png(tmp_path / "a.png", 30, 20, dpi=300))
    assert (i.width, i.height, i.format) == (30, 20, "png") and i.dpi == pytest.approx(300, abs=0.1)
    assert image_info(png(tmp_path / "c.png", 5, 5)).dpi is None
    j = image_info(jpeg(tmp_path / "a.jpg", 640, 480, dpi=600))
    assert (j.width, j.height, j.dpi) == (640, 480, 600)
    w = image_info(webp(tmp_path / "a.webp", 1200, 1800))
    assert (w.width, w.height, w.dpi) == (1200, 1800, None)
    with pytest.raises(ValueError):
        (tmp_path / "x.png").write_bytes(b"not an image")
        image_info(str(tmp_path / "x.png"))


def test_page_size_comes_from_the_art():
    from cpb_core.art import ImageInfo
    info = ImageInfo(width=4110, height=6283, dpi=600, format="png")  # 174 x 266 mm
    size, rect = art_size(info, dpi=None, fallback_dpi=300, bleed=3, includes_bleed=True, safe=5, margin=8)
    assert (size.trim_w, size.trim_h) == pytest.approx((4110 * MM_PER_INCH / 600 - 6, 6283 * MM_PER_INCH / 600 - 6), abs=0.001)
    assert (rect.x, rect.y) == (0, 0) and rect.w == pytest.approx(size.canvas_w, abs=0.001)
    size2, rect2 = art_size(info, dpi=None, fallback_dpi=300, bleed=3, includes_bleed=False, safe=5, margin=8)
    assert (rect2.x, rect2.y) == (3, 3) and size2.trim_w == pytest.approx(rect2.w)
    # No resolution in the file: the override, then the project's.
    bare = ImageInfo(width=600, height=900, dpi=None, format="webp")
    assert art_size(bare, dpi=None, fallback_dpi=300, bleed=0, includes_bleed=True, safe=5, margin=8)[0].trim_w == pytest.approx(50.8)
    assert art_size(bare, dpi=150, fallback_dpi=300, bleed=0, includes_bleed=True, safe=5, margin=8)[0].trim_w == pytest.approx(101.6)


def test_drawn_page_in_a_project(tmp_path):
    p = create_project(str(tmp_path / "C"), "C", blank_pages=1, seed=1)
    src = png(tmp_path / "scan.png", 400, 600, dpi=100)
    page = p.add_art_page(src, includes_bleed=False)
    assert page.number == 2 and page.is_art and page.cells == ()
    assert p.entry(2).status == "letters"
    art = p.art_path(page)
    assert art.endswith("page_02_art.png") and open(art, "rb").read() == open(src, "rb").read()
    again = load_project(p.folder).load_page(2)
    assert again.art == page.art and again.size == page.size
    svg = open(p.page_path(2), encoding="utf-8").read()
    assert 'xlink:href="page_02_art.png"' in svg and "cpb-panel-" not in svg


def test_art_survives_a_round_trip_and_balloon_saves(tmp_path):
    p = create_project(str(tmp_path / "C"), "C")
    page = p.add_art_page(png(tmp_path / "s.png", 200, 300, dpi=72), includes_bleed=True)
    doc = parse_page(page_to_svg(page))
    assert doc.page == page and doc.to_svg() == page_to_svg(page)
    from cpb_core.balloons import Balloon
    p.save_balloons(1, [Balloon(1, cx=20, cy=20, text="HI")])
    assert p.load_page(1).art == page.art
