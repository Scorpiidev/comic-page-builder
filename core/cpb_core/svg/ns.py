"""XML namespaces and small helpers shared by the SVG writer and reader."""

from __future__ import annotations

import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
CPB = "https://github.com/Scorpiidev/comic-page-builder/ns/1"

FORMAT = "cpb-page"
FORMAT_VERSION = 1

KNOWN_PREFIXES = {"": SVG, "xlink": XLINK, "inkscape": INKSCAPE, "sodipodi": SODIPODI, "cpb": CPB}
for _prefix, _uri in KNOWN_PREFIXES.items():
    ET.register_namespace(_prefix, _uri)


def q(ns: str, name: str) -> str:
    """Qualified ElementTree name, e.g. q(CPB, 'cell') -> '{...}cell'."""
    return f"{{{ns}}}{name}"


def num(x: float) -> str:
    """Compact, stable number formatting: 3 decimals, no trailing zeros."""
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def frac(x: float) -> str:
    """Cell fractions keep 6 decimals so layouts round-trip exactly."""
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def is_owned(el: ET.Element) -> bool:
    return el.get("id", "").startswith("cpb-")
