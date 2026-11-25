"""
Balloon outlines as SVG path data.

Each balloon is **one path**: the body is split where the tail leaves it and
the tail is drawn into the gap, so the stroke goes round the tail instead of
crossing the joint, and no boolean-operation library is needed (DESIGN.md
section 10). Thought balloons are the exception: their tail is a trail of
separate little bubbles, written as extra subpaths of the same path.

Only absolute M, L, C and Z commands are used, never arcs (A). Photoshop's
importer has to turn paths into its own anchor points, and cubic curves map
onto those one to one; arcs would need converting in JavaScript, and the
importers never compute geometry (rule in CLAUDE.md).
"""

from __future__ import annotations

import math
import random
from typing import Optional

from .model import Balloon

Point = tuple[float, float]
TWO_PI = 2 * math.pi


def num(x: float) -> str:
    # Same formatting as svg/ns.py. Copied, not imported: importing the svg
    # package from here would loop, because the svg writer imports balloons.
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _p(pt: Point) -> str:
    return f"{num(pt[0])} {num(pt[1])}"


class _Ellipse:
    """An axis-aligned ellipse, worked in its "parameter" angle t, not the visual angle."""

    def __init__(self, cx: float, cy: float, rx: float, ry: float) -> None:
        self.cx, self.cy, self.rx, self.ry = cx, cy, rx, ry

    def at(self, t: float) -> Point:
        return self.cx + self.rx * math.cos(t), self.cy + self.ry * math.sin(t)

    def tangent(self, t: float) -> Point:
        return -self.rx * math.sin(t), self.ry * math.cos(t)

    def normal(self, t: float) -> Point:
        """Outward unit normal at t."""
        nx, ny = self.ry * math.cos(t), self.rx * math.sin(t)
        length = math.hypot(nx, ny) or 1.0
        return nx / length, ny / length

    def param_towards(self, x: float, y: float) -> float:
        """The parameter angle of the rim point in the direction of (x, y)."""
        return math.atan2((y - self.cy) / self.ry, (x - self.cx) / self.rx)

    def param_of_direction(self, degrees: float) -> float:
        a = math.radians(degrees)
        return math.atan2(self.rx * math.sin(a), self.ry * math.cos(a))

    def inside(self, x: float, y: float, margin: float = 1.0) -> bool:
        return ((x - self.cx) / self.rx) ** 2 + ((y - self.cy) / self.ry) ** 2 <= margin ** 2

    def arc(self, t1: float, t2: float) -> str:
        """Cubic curves from t1 to t2 (either direction), in pieces of at most 90 degrees."""
        pieces = max(1, math.ceil(abs(t2 - t1) / (math.pi / 2) - 1e-9))
        step = (t2 - t1) / pieces
        # The standard constant that makes a cubic hug a circular arc of this angle.
        k = 4 / 3 * math.tan(step / 4)
        out = []
        for i in range(pieces):
            a, b = t1 + i * step, t1 + (i + 1) * step
            (x1, y1), (x2, y2) = self.at(a), self.at(b)
            (dx1, dy1), (dx2, dy2) = self.tangent(a), self.tangent(b)
            out.append(f"C{_p((x1 + k * dx1, y1 + k * dy1))} {_p((x2 - k * dx2, y2 - k * dy2))} {_p((x2, y2))}")
        return "".join(out)

    def full(self) -> str:
        return f"M{_p(self.at(0))}{self.arc(0, TWO_PI)}Z"


def _tail_base(e: _Ellipse, b: Balloon) -> Optional[tuple[float, float]]:
    """(centre parameter, half width as a parameter angle) of where the tail joins the body, or None."""
    if not b.has_tail:
        return None
    tail = b.tail
    # A tip inside (or right on) the body would fold the tail back over the balloon.
    if e.inside(tail.tip_x, tail.tip_y, 1.05):
        return None
    t0 = e.param_towards(tail.tip_x, tail.tip_y) if tail.base_angle is None else e.param_of_direction(tail.base_angle)
    speed = math.hypot(*e.tangent(t0)) or 1.0  # mm of rim per radian here
    half = min(0.6, tail.base_width / 2 / speed)
    return t0, half


def _bent_side(start: Point, tip: Point, bend: float, sideways: Point) -> str:
    """One side of a tail: a curve from start to tip, pushed sideways by the bend."""
    length = math.hypot(tip[0] - start[0], tip[1] - start[1])
    qx = (start[0] + tip[0]) / 2 + sideways[0] * bend * length * 0.3
    qy = (start[1] + tip[1]) / 2 + sideways[1] * bend * length * 0.3
    # A quadratic curve written as a cubic, so the path keeps to M/L/C/Z.
    c1 = (start[0] + 2 / 3 * (qx - start[0]), start[1] + 2 / 3 * (qy - start[1]))
    c2 = (tip[0] + 2 / 3 * (qx - tip[0]), tip[1] + 2 / 3 * (qy - tip[1]))
    return f"C{_p(c1)} {_p(c2)} {_p(tip)}"


def _sideways(base: Point, tip: Point) -> Point:
    dx, dy = tip[0] - base[0], tip[1] - base[1]
    length = math.hypot(dx, dy) or 1.0
    return -dy / length, dx / length


def _speech(b: Balloon) -> str:
    e = _Ellipse(b.cx, b.cy, b.rx, b.ry)
    base = _tail_base(e, b)
    if base is None:
        return e.full()
    t0, half = base
    tip = (b.tail.tip_x, b.tail.tip_y)
    side = _sideways(e.at(t0), tip)
    start, end = e.at(t0 + half), e.at(t0 - half)
    # The long way round the body, then down one side of the tail and back up the other.
    return (f"M{_p(start)}{e.arc(t0 + half, t0 - half + TWO_PI)}"
            f"{_bent_side(end, tip, b.tail.bend, side)}{_bent_side(tip, start, b.tail.bend, side)}Z")


def _caption(b: Balloon) -> str:
    x0, y0, x1, y1 = b.cx - b.rx, b.cy - b.ry, b.cx + b.rx, b.cy + b.ry
    return f"M{_p((x0, y0))}L{_p((x1, y0))}L{_p((x1, y1))}L{_p((x0, y1))}Z"


def _thought(b: Balloon) -> str:
    e = _Ellipse(b.cx, b.cy, b.rx, b.ry)
    perimeter = math.pi * (3 * (b.rx + b.ry) - math.sqrt((3 * b.rx + b.ry) * (b.rx + 3 * b.ry)))
    bumps = max(7, round(perimeter / 7.0))
    ts = [TWO_PI * i / bumps for i in range(bumps + 1)]
    out = [f"M{_p(e.at(0))}"]
    for a, c in zip(ts, ts[1:]):
        p1, p2 = e.at(a), e.at(c)
        chord = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        h = chord * 0.55  # how far each bump puffs out: about half its width
        n1, n2 = e.normal(a), e.normal(c)
        out.append(f"C{_p((p1[0] + n1[0] * h, p1[1] + n1[1] * h))} {_p((p2[0] + n2[0] * h, p2[1] + n2[1] * h))} {_p(p2)}")
    out.append("Z")

    base = _tail_base(e, b)
    if base is not None:
        t0, _half = base
        tip = (b.tail.tip_x, b.tail.tip_y)
        rim = e.at(t0)
        side = _sideways(rim, tip)
        length = math.hypot(tip[0] - rim[0], tip[1] - rim[1])
        big = min(3.0, 0.2 * min(b.rx, b.ry), length / 4)
        sizes = [big, big * 0.62, max(0.6, big * 0.38)]
        for i, r in enumerate(sizes):
            f = (i + 1) / len(sizes)  # 1/3, 2/3, 1: the last bubble sits on the tip
            push = math.sin(f * math.pi) * b.tail.bend * length * 0.3
            x = rim[0] + (tip[0] - rim[0]) * f + side[0] * push
            y = rim[1] + (tip[1] - rim[1]) * f + side[1] * push
            if i == len(sizes) - 1:
                x, y = tip[0] - (tip[0] - rim[0]) / length * r, tip[1] - (tip[1] - rim[1]) / length * r
            out.append(_Ellipse(x, y, r, r).full())
    return "".join(out)


def _shout(b: Balloon) -> str:
    e = _Ellipse(b.cx, b.cy, b.rx, b.ry)
    perimeter = math.pi * (3 * (b.rx + b.ry) - math.sqrt((3 * b.rx + b.ry) * (b.rx + 3 * b.ry)))
    spikes = max(10, round(perimeter / 6.0))
    # Seeded by the balloon's number: the burst looks hand-made but is the
    # same every time the page is saved, so files don't change for nothing.
    rng = random.Random(b.number * 7919 + spikes)
    reach = [1.22 + rng.uniform(-0.08, 0.08) for _ in range(spikes)]
    base = _tail_base(e, b)
    tail_spike = None
    if base is not None:
        t0 = base[0] % TWO_PI
        tail_spike = round(t0 / TWO_PI * spikes) % spikes
    pts = []
    for i in range(spikes):
        t_out = TWO_PI * i / spikes
        t_in = TWO_PI * (i + 0.5) / spikes
        if i == tail_spike:
            pts.append((b.tail.tip_x, b.tail.tip_y))  # the spike that points at the speaker
        else:
            x, y = e.at(t_out)
            pts.append((b.cx + (x - b.cx) * reach[i], b.cy + (y - b.cy) * reach[i]))
        # Inner corners sit on the ellipse itself, which is what the text was fitted to.
        pts.append(e.at(t_in))
    return "M" + "L".join(_p(p) for p in pts) + "Z"


_SHAPES = {"speech": _speech, "whisper": _speech, "caption": _caption, "thought": _thought, "shout": _shout}


def outline_path(b: Balloon) -> str:
    """The balloon's outline, body and tail together, as SVG path data."""
    return _SHAPES[b.kind](b)
