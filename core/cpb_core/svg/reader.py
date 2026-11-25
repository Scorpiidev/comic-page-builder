"""
Read a page.svg back into a ``Page``, keeping everything the hub doesn't own.

``read_page`` returns a ``PageDocument``: the parsed ``Page`` plus the whole
XML tree. Saving the document again (``doc.to_svg()``) rewrites only the
``cpb-`` elements, so a sketch layer, a logo or a comment you added in
another app is still there afterwards.
"""

from __future__ import annotations

import io
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from typing import Optional, Union

from ..art import Art
from ..geometry import PageSize, Rect
from ..layouts.cells import Cell
from ..model import Page, PanelStyle
from .ns import BORDERS_FORMAT, CPB, FORMAT, FORMAT_VERSION, KNOWN_PREFIXES, SVG, XLINK, is_owned, q
from .letters import read_balloons
from .writer import LAYERS, apply_page, panel_path, serialize

_NS_N = re.compile(r"^ns\d+$")
HUB_LAYERS = {layer_id for layer_id, _ in LAYERS}


@dataclass
class PageDocument:
    page: Page
    root: ET.Element
    # Panels whose shape was changed outside the hub. Saving from the hub
    # redraws them from the layout, so the UI should ask before it does.
    modified_panels: list[int] = field(default_factory=list)
    # Balloons whose words were changed in another app (their text wins).
    edited_balloons: list[int] = field(default_factory=list)

    def foreign_elements(self) -> list[ET.Element]:
        """
        Elements the hub doesn't own: anything you added in another app.

        Hub layers are containers, so what you put inside them is still yours.
        Children of other hub elements (like the path inside a clip path) are
        part of that element and not counted.
        """
        parent = {child: el for el in self.root.iter() for child in el}

        def inside_owned_item(el: ET.Element) -> bool:
            p = parent.get(el)
            while p is not None and p is not self.root:
                if is_owned(p) and p.get("id") not in HUB_LAYERS:
                    return True
                p = parent.get(p)
            return False

        return [el for el in self.root.iter()
                if el is not self.root and not is_owned(el)
                and el.tag != q(SVG, "defs") and not inside_owned_item(el)]

    def letters_svg(self, balloons) -> str:
        """
        Serialize with only the Letters layer rewritten to ``balloons``.

        Saving lettering this way can't redraw a panel you reshaped in
        Illustrator: panels, guides and paper stay exactly as they are in the file.
        """
        from .letters import apply_balloons
        from .writer import _layer
        apply_balloons(_layer(self.root, "cpb-letters", "Letters"), balloons)
        self.page = replace(self.page, balloons=tuple(balloons) or None)
        return serialize(self.root)

    def to_svg(self, page: Optional[Page] = None) -> str:
        """Serialize, after writing ``page`` (default: the page as read) into the tree."""
        apply_page(self.root, page or self.page)
        return serialize(self.root)


def _find(root: ET.Element, el_id: str) -> Optional[ET.Element]:
    for el in root.iter():
        if el.get("id") == el_id:
            return el
    return None


def _register_namespaces(text: str) -> None:
    """Keep the file's own prefixes (inkscape:, i:, x: ...) instead of ns0:, ns1:."""
    for _event, (prefix, uri) in ET.iterparse(io.StringIO(text), events=("start-ns",)):
        if _NS_N.match(prefix or ""):
            continue
        if prefix in KNOWN_PREFIXES and KNOWN_PREFIXES[prefix] != uri:
            continue  # don't let a file steal our prefixes
        try:
            ET.register_namespace(prefix or "", uri)
        except ValueError:
            pass


def _parse(text: str) -> ET.Element:
    _register_namespaces(text)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    parser.feed(text)
    return parser.close()


def _float(el: ET.Element, name: str, default: Optional[float] = None) -> float:
    raw = el.get(q(CPB, name))
    if raw is None:
        if default is None:
            raise ValueError(f"the page is missing its cpb:{name} value")
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"cpb:{name} should be a number, got {raw!r}") from None


def read_page(path: Union[str, os.PathLike]) -> PageDocument:
    """Read a page.svg file. See ``parse_page`` for the errors it can raise."""
    with open(path, "r", encoding="utf-8") as f:
        return parse_page(f.read())


def parse_page(text: Union[str, bytes]) -> PageDocument:
    """
    Parse page.svg text.

    Raises ``ValueError`` with a plain explanation when the text isn't a hub
    page or is damaged.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    try:
        root = _parse(text)
    except ET.ParseError as e:
        raise ValueError(f"this isn't valid SVG/XML ({e})") from None

    if root.tag != q(SVG, "svg"):
        raise ValueError("this file isn't an SVG")
    if root.get(q(CPB, "format")) == BORDERS_FORMAT:
        raise ValueError("this is a borders-only export for Clip Studio Paint; open the page.svg it was made from")
    if root.get(q(CPB, "format")) != FORMAT:
        raise ValueError("this SVG wasn't made by Comic Page Builder (it has no cpb:format attribute)")
    version = int(root.get(q(CPB, "version"), "1"))
    if version > FORMAT_VERSION:
        raise ValueError(f"this page was saved by a newer version (format {version}); update Comic Page Builder")

    size = PageSize(trim_w=_float(root, "trim-w"), trim_h=_float(root, "trim-h"),
                    bleed=_float(root, "bleed"), safe=_float(root, "safe"),
                    margin=_float(root, "margin"), dpi=int(_float(root, "dpi")))
    number = int(_float(root, "page", 1))

    group = _find(root, "cpb-panels")
    if group is None:
        raise ValueError("the page has no Panels layer (cpb-panels)")
    paths = sorted((el for el in group if el.get("id", "").startswith("cpb-panel-")),
                   key=lambda el: int(el.get(q(CPB, "index"), "0")))
    cells = []
    for el in paths:
        raw = el.get(q(CPB, "cell"))
        if raw is None:
            raise ValueError(f"panel {el.get('id')} has no cpb:cell value")
        x, y, w, h = (float(v) for v in raw.split())
        cells.append(Cell(x, y, w, h))

    first = paths[0] if paths else None
    fill = first.get("fill") if first is not None else None
    style = PanelStyle(
        stroke=first.get("stroke", "#1b1b1b") if first is not None else "#1b1b1b",
        stroke_width=float(first.get("stroke-width", "0.6")) if first is not None else 0.6,
        fill=None if fill in (None, "none") else fill,
        corner_radius=_float(group, "radius", 0.0),
    )
    try:
        layout = json.loads(group.get(q(CPB, "layout"), "{}"))
    except json.JSONDecodeError:
        raise ValueError("the Panels layer has a damaged cpb:layout value") from None

    balloons, edited = read_balloons(_find(root, "cpb-letters"))
    art = None
    image = _find(root, "cpb-art-image")
    if image is not None:
        try:
            px_w, px_h = (int(v) for v in image.get(q(CPB, "px"), "0 0").split())
            art = Art(href=image.get(q(XLINK, "href")) or image.get("href", ""),
                      rect=Rect(float(image.get("x", 0)), float(image.get("y", 0)),
                                float(image.get("width")), float(image.get("height"))), px_w=px_w, px_h=px_h)
        except (TypeError, ValueError):
            raise ValueError("the Art layer's image has a damaged size") from None
    page = Page(number=number, size=size, cells=tuple(cells), gutter=_float(group, "gutter", 3.0),
                reading=group.get(q(CPB, "reading"), "ltr"), style=style, layout=layout,
                # No balloons reads as None ("nothing to change"), so a page
                # read back equals the page that was written.
                balloons=balloons or None, art=art)

    # A panel counts as edited elsewhere when its path no longer matches what the hub would draw.
    expected = {p.index: panel_path(page, p.rect) for p in page.panels()}
    modified = [int(el.get(q(CPB, "index"))) for el in paths
                if el.get("d") != expected.get(int(el.get(q(CPB, "index"), "0")))]
    return PageDocument(page=page, root=root, modified_panels=modified, edited_balloons=edited)
