"""
Balloons: speech, caption, thought, shout and whisper (docs/DESIGN.md section 10).

    model.py   Balloon and Tail: a balloon is stored as parameters, not a path,
               so the hub can edit body and tail separately (D6) and redraw it
    shapes.py  the outline: body and tail as one path, so the stroke never
               crosses the joint
    text.py    line breaking and fitting the body around the text

Everything is in millimetres, like the rest of the core. Text widths come from
a "measure" function the caller passes in: the hub measures with Qt, which
knows the real glyph widths; the core only has a rough estimate
(``approx_measure``), because reading glyph widths needs more of the font
file than the standard-library reader in lettering/fonts.py looks at.
"""

from .model import KINDS, Balloon, BalloonFont, Tail
from .shapes import outline_path, tail_base_point
from .text import TextBlock, approx_measure, fit_balloon, layout_lines, wrap

__all__ = ["KINDS", "Balloon", "BalloonFont", "Tail", "outline_path", "tail_base_point",
           "TextBlock", "approx_measure", "fit_balloon", "layout_lines", "wrap"]
