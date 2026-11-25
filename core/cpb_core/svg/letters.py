"""
The Letters layer: balloons in page.svg (DESIGN.md section 5.3).

Each balloon is a group holding one outline path and one text::

    <g id="cpb-balloon-3" class="cpb-balloon" cpb:kind="speech" cpb:body="cx cy rx ry" ...>
      <path id="cpb-balloon-3-outline" d="M... C... Z"/>
      <text id="cpb-balloon-3-text"><tspan x=".." y="..">LINE ONE</tspan>...</text>
    </g>

- The parameters live on the group (``cpb:`` attributes), so the hub can
  rebuild the balloon after an edit: the path alone couldn't tell it where
  the tail's tip was.
- Text is pre-broken into tspans with explicit x and y. SVG 1.1 has no text
  wrapping, and fixed lines stop each app re-wrapping the text its own way.
- Ownership: only groups with a ``cpb-balloon-`` id are the hub's. Anything
  else you put in the Letters layer (a hand-drawn SFX, say) is left alone.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from typing import Optional

from ..balloons import Balloon, BalloonFont, Tail, approx_measure, fit_balloon, layout_lines, outline_path
from ..balloons.text import text_width_for, wrap
from ..units import MM_PER_PT
from .ns import CPB, SVG, num, q

PREFIX = "cpb-balloon-"
CLASS = "cpb-balloon"
WHISPER_DASH = "1.2 0.9"  # mm


def _n(v):
    """A number for the JSON attributes, written the same way however it was typed (75, 75.0)."""
    if v is None:
        return None
    r = round(float(v), 3)
    return int(r) if r == int(r) else r


def _is_balloon(el: ET.Element) -> bool:
    return el.get("id", "").startswith(PREFIX)


def _laid_out(b: Balloon) -> Balloon:
    """Make sure b has lines; balloons that never met the hub's font metrics get the rough estimate."""
    if b.lines is not None:
        return b
    return fit_balloon(b, approx_measure(b.font.size_pt))


def balloon_element(b: Balloon) -> ET.Element:
    b = _laid_out(b)
    bid = f"{PREFIX}{b.number}"
    g = ET.Element(q(SVG, "g"), {"id": bid, "class": CLASS})
    g.set(q(CPB, "number"), str(b.number))
    g.set(q(CPB, "kind"), b.kind)
    g.set(q(CPB, "text-role"), b.role)
    g.set(q(CPB, "body"), " ".join(num(v) for v in (b.cx, b.cy, b.rx, b.ry)))
    g.set(q(CPB, "auto"), "true" if b.auto_size else "false")
    # The text as typed, line breaks included (ElementTree writes them as &#10;).
    g.set(q(CPB, "text"), b.text)
    f = b.font
    g.set(q(CPB, "font"), json.dumps({"family": f.family, "style": f.style, "ps_name": f.ps_name, "size_pt": _n(f.size_pt),
                                      "cap_ratio": _n(f.cap_ratio), "leading": _n(f.leading)},
                                     sort_keys=True, separators=(",", ":")))
    if b.tail is not None:
        t = b.tail
        g.set(q(CPB, "tail"), json.dumps({"tip": [_n(t.tip_x), _n(t.tip_y)],
                                          "base_width": _n(t.base_width), "bend": _n(t.bend),
                                          "base_angle": _n(t.base_angle), "follows": t.tip_follows_body},
                                         sort_keys=True, separators=(",", ":")))

    path = {"id": f"{bid}-outline", "d": outline_path(b), "fill": b.fill or "none", "stroke": b.stroke,
            "stroke-width": num(b.stroke_width), "stroke-linejoin": "round"}
    if b.kind == "whisper":
        path["stroke-dasharray"] = WHISPER_DASH
    ET.SubElement(g, q(SVG, "path"), path)

    text = ET.SubElement(g, q(SVG, "text"), {
        "id": f"{bid}-text",
        "font-family": f.family,
        "font-size": num(f.size_pt * MM_PER_PT),  # user units are mm
        "text-anchor": "middle",
        "fill": f.color,
    })
    block = layout_lines(b.lines, b, approx_measure(f.size_pt))
    for line, y in zip(block.lines, block.baselines(b.cy)):
        span = ET.SubElement(text, q(SVG, "tspan"), {"x": num(b.cx), "y": num(y)})
        span.text = line
    return g


def apply_balloons(layer: ET.Element, balloons) -> None:
    """Replace the hub's balloons in the Letters layer; everything else in it stays."""
    for el in [c for c in layer if _is_balloon(c)]:
        layer.remove(el)
    for i, b in enumerate(balloons):
        layer.insert(i, balloon_element(b))


def _json(el: ET.Element, name: str) -> Optional[dict]:
    raw = el.get(q(CPB, name))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"balloon {el.get('id')} has a damaged cpb:{name} value") from None


def read_balloons(layer: Optional[ET.Element]) -> tuple[tuple[Balloon, ...], list[int]]:
    """(balloons, numbers of balloons whose text was edited in another app)."""
    if layer is None:
        return (), []
    out, edited = [], []
    for g in layer:
        if not _is_balloon(g) or g.tag != q(SVG, "g"):
            continue
        try:
            number = int(g.get(q(CPB, "number"), g.get("id")[len(PREFIX):]))
            cx, cy, rx, ry = (float(v) for v in g.get(q(CPB, "body"), "").split())
        except ValueError:
            raise ValueError(f"balloon {g.get('id')} has a damaged cpb:body or cpb:number value") from None
        fd = _json(g, "font") or {}
        text_el = next((c for c in g if c.tag == q(SVG, "text")), None)
        color = text_el.get("fill", "#1b1b1b") if text_el is not None else "#1b1b1b"
        font = BalloonFont(family=fd.get("family", "Comic Neue"), style=fd.get("style", "Regular"),
                           ps_name=fd.get("ps_name", ""),
                           size_pt=float(fd.get("size_pt", 8.0)), cap_ratio=float(fd.get("cap_ratio", 0.7)),
                           leading=float(fd.get("leading", 1.2)), color=color)
        td = _json(g, "tail")
        tail = None
        if td is not None:
            tail = Tail(tip_x=float(td["tip"][0]), tip_y=float(td["tip"][1]),
                        base_width=float(td.get("base_width", 6.0)), bend=float(td.get("bend", 0.0)),
                        base_angle=td.get("base_angle"), tip_follows_body=bool(td.get("follows", False)))
        outline = next((c for c in g if c.tag == q(SVG, "path")), None)
        fill = outline.get("fill") if outline is not None else None
        lines = tuple("".join(span.itertext()) for span in text_el if span.tag == q(SVG, "tspan")) \
            if text_el is not None else ()
        text = g.get(q(CPB, "text"), "\n".join(lines))
        if text.split() != " ".join(lines).split():
            # Someone changed the words in Illustrator (or similar): their
            # version wins, and the hub can say so.
            text = "\n".join(lines)
            edited.append(number)
        out.append(Balloon(
            number=number, kind=g.get(q(CPB, "kind"), "speech"), cx=cx, cy=cy, rx=rx, ry=ry,
            text=text, role=g.get(q(CPB, "text-role"), "dialogue"), font=font, tail=tail,
            auto_size=g.get(q(CPB, "auto"), "true") == "true",
            stroke=outline.get("stroke", "#1b1b1b") if outline is not None else "#1b1b1b",
            stroke_width=float(outline.get("stroke-width", "0.35")) if outline is not None else 0.35,
            fill=None if fill in (None, "none") else fill,
            lines=lines,
        ))
    return tuple(out), edited


def next_number(balloons) -> int:
    return max((b.number for b in balloons), default=0) + 1
