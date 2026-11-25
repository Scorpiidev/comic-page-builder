"""
Breaking balloon text into lines and fitting the body around it.

1. Break lines greedily: as many words per line as fit the width.
2. Measure the block of lines, w x h.
3. Fit the body around it. An ellipse with half axes w/sqrt(2) and h/sqrt(2)
   passes exactly through the block's corners (DESIGN.md section 10); padding
   goes on top.

Auto-sized balloons try a range of widths and keep the one with the smallest
body that still has a comic-balloon shape (wider than tall, but not a sausage).

The block's height runs from the top of the capitals on the first line to the
baseline of the last line. Comic lettering is usually all caps, so that is the
ink you actually see, and centring it centres the text visually.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable

from ..units import MM_PER_PT
from .model import Balloon

# measure(text) -> width in mm at the balloon's font size.
Measure = Callable[[str], float]

SQRT2 = math.sqrt(2)
IDEAL_ASPECT = 1.5   # body width / height that reads as a speech balloon
PADDING = {"speech": 2.0, "whisper": 2.0, "caption": 1.8, "thought": 3.0, "shout": 2.5}  # mm


def approx_measure(size_pt: float, width_ratio: float = 0.6) -> Measure:
    """
    A rough width estimate: every character is ``width_ratio`` of the em.

    Good enough for tests and the command line. The hub passes Qt's real
    measurements instead, so line breaks match the font.
    """
    em = size_pt * MM_PER_PT
    return lambda s: len(s) * em * width_ratio


def wrap(text: str, measure: Measure, max_width: float) -> list[str]:
    """Greedy line breaks. Typed line breaks are kept; a word wider than the line gets a line of its own."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if measure(candidate) <= max_width + 1e-9:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    # Blank lines at the ends only push the text off-centre.
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return lines


@dataclass(frozen=True)
class TextBlock:
    lines: tuple[str, ...]
    width: float          # widest line, mm
    height: float         # cap top of the first line to the baseline of the last, mm
    line_height: float    # baseline to baseline, mm
    cap: float            # cap height, mm

    def baselines(self, cy: float) -> list[float]:
        """The y of each line's baseline, with the block centred on cy."""
        top = cy - self.height / 2
        return [top + self.cap + i * self.line_height for i in range(len(self.lines))]


def layout_lines(lines: list[str] | tuple[str, ...], b: Balloon, measure: Measure) -> TextBlock:
    size_mm = b.font.size_pt * MM_PER_PT
    lh = size_mm * b.font.leading
    cap = size_mm * b.font.cap_ratio
    lines = tuple(lines)
    width = max((measure(s) for s in lines), default=0.0)
    height = cap + lh * (len(lines) - 1) if lines else 0.0
    return TextBlock(lines, width, height, lh, cap)


def _body_for(block: TextBlock, kind: str) -> tuple[float, float]:
    """Half width and half height of the body that holds the block."""
    pad = PADDING[kind]
    w, h = max(block.width, 1.0), max(block.height, 1.0)
    if kind == "caption":
        return w / 2 + pad, h / 2 + pad
    return w / SQRT2 + pad, h / SQRT2 + pad


def text_width_for(b: Balloon) -> float:
    """How wide a line can be inside a body of b's current size (the inverse of _body_for)."""
    pad = PADDING[b.kind]
    if b.kind == "caption":
        return max(1.0, 2 * (b.rx - pad))
    return max(1.0, SQRT2 * (b.rx - pad))


def fit_balloon(b: Balloon, measure: Measure) -> Balloon:
    """
    Lay out b's text: fills in ``lines``, and the body size when auto-size is on.

    With auto-size off, the body keeps its size and the text wraps to it.
    """
    if not b.text.strip():
        return replace(b, lines=())
    if not b.auto_size:
        return replace(b, lines=tuple(wrap(b.text, measure, text_width_for(b))))

    words = b.text.split()
    narrowest = max(measure(w) for w in words)
    widest = max(measure(p) for p in b.text.split("\n"))
    best = None
    steps = 24
    for i in range(steps + 1):
        limit = narrowest + (widest - narrowest) * i / steps
        block = layout_lines(wrap(b.text, measure, limit), b, measure)
        rx, ry = _body_for(block, b.kind)
        # Smallest area wins, with a penalty for drifting from a balloon-ish shape.
        score = rx * ry * (1 + 2 * abs(math.log((rx / ry) / IDEAL_ASPECT)))
        if best is None or score < best[0] - 1e-9:
            best = (score, block, rx, ry)
    _score, block, rx, ry = best
    return replace(b, lines=block.lines, rx=round(rx, 3), ry=round(ry, 3))
