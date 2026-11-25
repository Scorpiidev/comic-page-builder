"""
A balloon as parameters (docs/DESIGN.md section 10, decision D6).

The body and the tail are separate on purpose: lettering means placing the
body for reading flow and the tail for the speaker. Moving the body leaves the
tail's tip where it was (still pointing at the speaker), unless
``tip_follows_body`` is on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Optional

KINDS = ("speech", "caption", "thought", "shout", "whisper")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Tail:
    tip_x: float               # where the tail points (the speaker's mouth), canvas mm
    tip_y: float
    base_width: float = 6.0    # mm along the rim where the tail leaves the body
    bend: float = 0.0          # -1..1: how far the tail curves sideways, 0 = straight
    # Where on the rim the tail starts, in degrees (0 = right, 90 = down,
    # because SVG's y axis points down). None aims it straight at the tip,
    # which is what you want most of the time.
    base_angle: Optional[float] = None
    tip_follows_body: bool = False

    def __post_init__(self) -> None:
        if self.base_width <= 0:
            raise ValueError("a tail's base width has to be more than 0 mm")
        if not -1.0 <= self.bend <= 1.0:
            raise ValueError("a tail's bend goes from -1 to 1")


@dataclass(frozen=True)
class BalloonFont:
    family: str = "Comic Neue"
    style: str = "Regular"     # "Bold", "Light Italic"...: the face within the family
    ps_name: str = ""          # what Photoshop and Illustrator call it (section 5.2)
    size_pt: float = 8.0       # at the canvas's own size, i.e. already the "working" size
    cap_ratio: float = 0.7     # cap height / em, from the lettering presets
    leading: float = 1.2       # line height as a multiple of the size
    color: str = "#1b1b1b"

    def __post_init__(self) -> None:
        if self.size_pt <= 0 or self.leading <= 0:
            raise ValueError("font size and leading have to be more than 0")
        if not _HEX.match(self.color):
            raise ValueError(f"text colour must look like #1b1b1b, got {self.color!r}")


@dataclass(frozen=True)
class Balloon:
    # The balloon's number is its identity (id "cpb-balloon-N"), like panel
    # numbers: it stays put when balloons are reordered or edited.
    number: int
    kind: str = "speech"
    cx: float = 0.0            # body centre, canvas mm
    cy: float = 0.0
    rx: float = 15.0           # half width and half height of the body
    ry: float = 10.0
    text: str = ""             # "\n" is a line break you typed; other breaks are automatic
    role: str = "dialogue"     # which lettering preset it uses
    font: BalloonFont = field(default_factory=BalloonFont)
    tail: Optional[Tail] = None
    # On: the body grows and shrinks with the text. Resizing by hand turns it
    # off and re-wraps the text inside the size you chose instead.
    auto_size: bool = True
    stroke: str = "#1b1b1b"
    stroke_width: float = 0.35
    fill: Optional[str] = "#ffffff"
    # The text as broken into lines. None means "not laid out yet"; the
    # writer then breaks it with the rough estimate. The hub fills it in with
    # real font widths (text.fit_balloon), so every app shows the same lines.
    lines: Optional[tuple[str, ...]] = None

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("balloon numbers start at 1")
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of: {', '.join(KINDS)}")
        if self.rx <= 0 or self.ry <= 0:
            raise ValueError("a balloon's body needs a size above 0 mm")
        if self.stroke_width < 0:
            raise ValueError("stroke width can't be negative")
        for name in ("stroke", "fill"):
            value = getattr(self, name)
            if value is not None and not _HEX.match(value):
                raise ValueError(f"{name} must be a colour like #1b1b1b, got {value!r}")

    @property
    def has_tail(self) -> bool:
        # Captions are narration boxes: they never point at anyone.
        return self.tail is not None and self.kind != "caption"

    def moved(self, dx: float, dy: float) -> "Balloon":
        """The balloon with its body moved; the tip stays unless it follows the body."""
        tail = self.tail
        if tail is not None and tail.tip_follows_body:
            tail = replace(tail, tip_x=tail.tip_x + dx, tip_y=tail.tip_y + dy)
        return replace(self, cx=self.cx + dx, cy=self.cy + dy, tail=tail)
