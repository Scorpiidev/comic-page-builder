"""
Page size and the rectangles derived from it.

``PageSize`` holds what the artist chooses. ``PageGeometry`` is the only place
that turns those choices into rectangles, so no other module repeats the
trim / bleed / safe / live arithmetic.

Coordinates are millimetres with the origin at the top-left corner of the
canvas (which includes the bleed), y growing downwards like SVG.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .units import mm_to_px


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return self.w * self.h

    def inset(self, d: float) -> "Rect":
        """Shrink by ``d`` on every side (negative grows it)."""
        return Rect(self.x + d, self.y + d, self.w - 2 * d, self.h - 2 * d)

    def contains(self, other: "Rect", tol: float = 1e-9) -> bool:
        return (other.x >= self.x - tol and other.y >= self.y - tol
                and other.right <= self.right + tol and other.bottom <= self.bottom + tol)

    def intersection_area(self, other: "Rect") -> float:
        w = min(self.right, other.right) - max(self.x, other.x)
        h = min(self.bottom, other.bottom) - max(self.y, other.y)
        return w * h if w > 0 and h > 0 else 0.0


@dataclass(frozen=True)
class PageSize:
    """
    What the artist picks for a page. All millimetres except ``dpi``.

    The canvas (manuscript) size is never stored: it is always
    trim + 2 x bleed, so the two can't drift apart.
    """

    trim_w: float
    trim_h: float
    bleed: float = 3.0
    safe: float = 5.0    # measured inside the trim, independent of bleed
    margin: float = 8.0  # trim edge to the outermost panel border
    dpi: int = 600

    def __post_init__(self) -> None:
        problems = []
        if self.trim_w <= 0 or self.trim_h <= 0:
            problems.append("trim width and height must be positive")
        for name in ("bleed", "safe", "margin"):
            if getattr(self, name) < 0:
                problems.append(f"{name} can't be negative")
        short = min(self.trim_w, self.trim_h)
        if 2 * self.margin >= short:
            problems.append("the margins leave no room for panels")
        if 2 * self.safe >= short:
            problems.append("the safe area leaves no room on the page")
        if not 72 <= self.dpi <= 2400:
            problems.append("resolution must be between 72 and 2400 dpi")
        if problems:
            raise ValueError("Invalid page size: " + "; ".join(problems) + ".")

    @property
    def canvas_w(self) -> float:
        return self.trim_w + 2 * self.bleed

    @property
    def canvas_h(self) -> float:
        return self.trim_h + 2 * self.bleed

    def canvas_px(self) -> tuple[int, int]:
        return mm_to_px(self.canvas_w, self.dpi), mm_to_px(self.canvas_h, self.dpi)

    def landscape(self) -> "PageSize":
        """The same page turned sideways (width >= height)."""
        if self.trim_w >= self.trim_h:
            return self
        return replace(self, trim_w=self.trim_h, trim_h=self.trim_w)

    def portrait(self) -> "PageSize":
        if self.trim_h >= self.trim_w:
            return self
        return replace(self, trim_w=self.trim_h, trim_h=self.trim_w)


@dataclass(frozen=True)
class PageGeometry:
    """Every guide rectangle of a page, in canvas millimetres."""

    size: PageSize
    canvas: Rect
    trim: Rect
    safe: Rect
    live: Rect  # where panels go: trim minus margins

    @classmethod
    def of(cls, size: PageSize) -> "PageGeometry":
        canvas = Rect(0.0, 0.0, size.canvas_w, size.canvas_h)
        trim = Rect(size.bleed, size.bleed, size.trim_w, size.trim_h)
        return cls(size=size, canvas=canvas, trim=trim,
                   safe=trim.inset(size.safe), live=trim.inset(size.margin))

    def panels_inside_safe_area(self) -> bool:
        """True when the live area sits fully inside the safe area."""
        return self.safe.contains(self.live)
