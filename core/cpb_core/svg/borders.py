"""
A borders-only SVG, so Clip Studio Paint gets editable vector panel borders.

CSP has no scripting, so a page reaches it as page.psd, and CSP turns the
PSD's shape layers into raster layers. Its File > Import > Vector... does keep
SVG paths as editable vector lines (M2 test, see importers/M2_RESULTS.md), but
it puts everything in the file on one layer, drops dashes, and turns
fill-only shapes (like the white paper) into 1 mm lines. So this file holds
only the panel outlines: stroke set, fill none, with no paper, guides, clip
paths or letters. It keeps page.svg's canvas and viewBox, so the lines land
exactly on the PSD's frames.

Like the importers, it draws from the hub's layout (each panel's final rect),
not from hand-edited paths, so it always matches the PSD.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Union

from ..model import Page
from .ns import BORDERS_FORMAT, CPB, SVG, num, q
from .writer import panel_d, serialize


def borders_svg(page: Page) -> str:
    st = page.style
    if st.stroke_width <= 0:
        raise ValueError("the panels have no border (stroke width 0), so there's nothing to export")
    s = page.size
    root = ET.Element(q(SVG, "svg"), {
        "width": f"{num(s.canvas_w)}mm",
        "height": f"{num(s.canvas_h)}mm",
        "viewBox": f"0 0 {num(s.canvas_w)} {num(s.canvas_h)}",
        # Marked as its own format, so nobody mistakes it for an editable page.
        q(CPB, "format"): BORDERS_FORMAT,
        q(CPB, "version"): "1",
        q(CPB, "page"): str(page.number),
    })
    for p in page.panels():
        ET.SubElement(root, q(SVG, "path"), {
            "id": f"cpb-border-{p.index}",
            "d": panel_d(page, p),
            # Panel fills belong to the PSD's Mask layers; CSP would turn a fill into a line.
            "fill": "none",
            "stroke": st.stroke,
            "stroke-width": num(st.stroke_width),
            "stroke-linejoin": "miter",
        })
    return serialize(root)


def borders_file_name(page_path: Union[str, os.PathLike]) -> str:
    """page_07.svg -> page_07_borders.svg, next to it. CSP names the new layer after the file."""
    stem, _ext = os.path.splitext(os.fspath(page_path))
    return f"{stem}_borders.svg"


def write_borders(page: Page, path: Union[str, os.PathLike]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(borders_svg(page))
