"""
Write a ``Page`` as SVG, or update an existing page.svg in place.

User units are millimetres (``width="174mm"`` with a matching ``viewBox``), so
every number in the file is the same millimetre value the core uses.

Layer stack, bottom to top (SVG paints later elements on top)::

    <defs>        cpb-clip-N   one clip path per panel, for the importers
    cpb-paper     white canvas, so the file previews correctly anywhere
    cpb-panels    one <path> per panel, in reading order
    cpb-letters   balloons and text (filled in by M5; never cleared here)
    cpb-guides    trim, safe area and crop marks; cpb:print="false"
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Optional

from ..geometry import Rect
from ..model import Page
from .ns import CPB, FORMAT, FORMAT_VERSION, INKSCAPE, SVG, frac, is_owned, num, q

LAYERS = [  # (id, label), bottom to top
    ("cpb-paper", "Paper"),
    ("cpb-panels", "Panels"),
    ("cpb-letters", "Letters"),
    ("cpb-guides", "Guides"),
]
GUIDE_TRIM = "#8a8a8f"
GUIDE_SAFE = "#00a6d6"
GUIDE_WIDTH = 0.25  # mm, hairline


def rect_path(r: Rect, radius: float = 0.0) -> str:
    """Path data for a rectangle, optionally with rounded corners."""
    rad = min(radius, r.w / 2, r.h / 2)
    if rad <= 0:
        return f"M{num(r.x)} {num(r.y)}H{num(r.right)}V{num(r.bottom)}H{num(r.x)}Z"
    a = f"A{num(rad)} {num(rad)} 0 0 1"
    return (f"M{num(r.x + rad)} {num(r.y)}H{num(r.right - rad)}{a} {num(r.right)} {num(r.y + rad)}"
            f"V{num(r.bottom - rad)}{a} {num(r.right - rad)} {num(r.bottom)}"
            f"H{num(r.x + rad)}{a} {num(r.x)} {num(r.bottom - rad)}"
            f"V{num(r.y + rad)}{a} {num(r.x + rad)} {num(r.y)}Z")


def panel_path(page: Page, rect: Rect) -> str:
    return rect_path(rect, page.style.corner_radius)


def _child(parent: ET.Element, tag: str, attrs: dict, index: Optional[int] = None) -> ET.Element:
    el = ET.Element(q(SVG, tag), {k: v for k, v in attrs.items() if v is not None})
    if index is None:
        parent.append(el)
    else:
        parent.insert(index, el)
    return el


def _find_by_id(root: ET.Element, el_id: str) -> Optional[ET.Element]:
    for el in root.iter():
        if el.get("id") == el_id:
            return el
    return None


def _clear_owned(group: ET.Element) -> None:
    for el in [c for c in group if is_owned(c)]:
        group.remove(el)


def _layer(root: ET.Element, layer_id: str, label: str) -> ET.Element:
    """Find a hub layer, or create it in its canonical place."""
    g = _find_by_id(root, layer_id)
    if g is None:
        g = ET.Element(q(SVG, "g"))
        g.set("id", layer_id)
        # Put it just above the previous hub layer that exists, else at the end.
        order = [lid for lid, _ in LAYERS]
        anchor_pos = None
        for lid in reversed(order[: order.index(layer_id)]):
            prev = _find_by_id(root, lid)
            if prev is not None and prev in list(root):
                anchor_pos = list(root).index(prev) + 1
                break
        if anchor_pos is None:
            anchor_pos = len(root) if layer_id != "cpb-paper" else _after_defs(root)
        root.insert(anchor_pos, g)
    g.set(q(INKSCAPE, "groupmode"), "layer")
    g.set(q(INKSCAPE, "label"), label)
    return g


def _after_defs(root: ET.Element) -> int:
    kids = list(root)
    for i, el in enumerate(kids):
        if el.tag == q(SVG, "defs"):
            return i + 1
    return 0


def _defs(root: ET.Element) -> ET.Element:
    for el in root:
        if el.tag == q(SVG, "defs"):
            return el
    d = ET.Element(q(SVG, "defs"))
    root.insert(0, d)
    return d


def apply_page(root: ET.Element, page: Page) -> None:
    """Write ``page`` into an SVG root, replacing only hub-owned elements."""
    s, g = page.size, page.geometry()
    root.set("width", f"{num(s.canvas_w)}mm")
    root.set("height", f"{num(s.canvas_h)}mm")
    root.set("viewBox", f"0 0 {num(s.canvas_w)} {num(s.canvas_h)}")
    for key, value in [("format", FORMAT), ("version", str(FORMAT_VERSION)), ("page", str(page.number)),
                       ("trim-w", num(s.trim_w)), ("trim-h", num(s.trim_h)), ("bleed", num(s.bleed)),
                       ("safe", num(s.safe)), ("margin", num(s.margin)), ("dpi", str(s.dpi))]:
        root.set(q(CPB, key), value)

    panels = page.panels()
    st = page.style

    # Clip paths for the importers (Photoshop vector masks, Illustrator clipping masks).
    defs = _defs(root)
    for el in [c for c in defs if c.get("id", "").startswith("cpb-clip-")]:
        defs.remove(el)
    for p in panels:
        clip = _child(defs, "clipPath", {"id": f"cpb-clip-{p.index}"})
        _child(clip, "path", {"d": panel_path(page, p.rect)})

    paper = _layer(root, "cpb-paper", "Paper")
    _clear_owned(paper)
    _child(paper, "rect", {"id": "cpb-paper-fill", "x": "0", "y": "0", "width": num(s.canvas_w),
                           "height": num(s.canvas_h), "fill": "#ffffff"}, index=0)

    pg = _layer(root, "cpb-panels", "Panels")
    pg.set(q(CPB, "gutter"), num(page.gutter))
    pg.set(q(CPB, "reading"), page.reading)
    pg.set(q(CPB, "radius"), num(st.corner_radius))
    pg.set(q(CPB, "layout"), json.dumps(page.layout, sort_keys=True, separators=(",", ":")))
    _clear_owned(pg)
    for i, p in enumerate(panels):
        c = p.cell
        _child(pg, "path", {
            "id": f"cpb-panel-{p.index}",
            q(CPB, "index"): str(p.index),
            q(CPB, "cell"): " ".join(frac(v) for v in (c.x, c.y, c.w, c.h)),
            "d": panel_path(page, p.rect),
            "fill": st.fill or "none",
            "stroke": st.stroke,
            "stroke-width": num(st.stroke_width),
            "stroke-linejoin": "miter",
        }, index=i)

    _layer(root, "cpb-letters", "Letters")  # owned by the balloon editor (M5)

    guides = _layer(root, "cpb-guides", "Guides")
    guides.set(q(CPB, "print"), "false")
    _clear_owned(guides)
    hair = {"fill": "none", "stroke-width": num(GUIDE_WIDTH)}
    _child(guides, "path", {"id": "cpb-trim", "d": rect_path(g.trim), "stroke": GUIDE_TRIM,
                            "stroke-dasharray": "2 1.4", **hair}, index=0)
    _child(guides, "path", {"id": "cpb-safe", "d": rect_path(g.safe), "stroke": GUIDE_SAFE,
                            "stroke-dasharray": "1.4 1.2", **hair}, index=1)
    marks = crop_marks(g.trim, s.bleed)
    if marks:
        _child(guides, "path", {"id": "cpb-crop-marks", "d": marks, "stroke": "#1b1b1b", **hair}, index=2)


def crop_marks(trim: Rect, bleed: float, gap: float = 1.0) -> str:
    """Corner marks in the bleed, starting ``gap`` mm outside the trim. Empty if the bleed is too thin."""
    length = min(5.0, (bleed - gap) * 0.9)
    if length < 0.5:
        return ""
    segs = []
    for x, sx in ((trim.x, -1), (trim.right, 1)):
        for y, sy in ((trim.y, -1), (trim.bottom, 1)):
            segs.append(f"M{num(x)} {num(y + sy * gap)}V{num(y + sy * (gap + length))}")
            segs.append(f"M{num(x + sx * gap)} {num(y)}H{num(x + sx * (gap + length))}")
    return "".join(segs)


def serialize(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def page_to_svg(page: Page) -> str:
    """A brand-new page.svg for ``page``."""
    root = ET.Element(q(SVG, "svg"))
    apply_page(root, page)
    return serialize(root)


def write_page(page: Page, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page_to_svg(page))
