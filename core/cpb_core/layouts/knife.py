"""
Manual layouts: cut panels with a knife at any angle, and add inset panels.

A manual layout is a **split tree**, like the random generator's, except
each cut is a line at any angle instead of only straight across:

    {"kind": "manual",
     "tree": {"cut": [x1, y1, x2, y2], "a": {...}, "b": {...}},   # or {} for an uncut panel
     "insets": [[x, y, w, h], ...]}

- Everything is stored in 0..1 coordinates of the live area and without
  gutters (D9), so changing the gutter, margins or page size re-flows the
  layout instead of breaking it.
- A cut is the whole line through its two points; it only splits the panel
  it was made in. Cutting a convex shape with a straight line gives two
  convex shapes, so every panel is a convex polygon. That keeps the gutter
  maths simple and exact (see ``_inset_polygon``).
- Edges made by a cut move in by half the gutter; edges on the live-area
  border stay put, exactly like ``cells.apply_gutter`` does for rectangles.
- Insets are panels that sit on top of the others (overlapping panels).
  Each inset has its own cut tree, in the inset's own 0..1 coordinates, so
  its cuts move and resize with it. With "inset_gap" on (the default) the
  writer draws a paper-coloured gap a gutter wide around each inset, so the
  lines behind it stop short of its border.

A cut is found by ``Where``: (inset index or -1 for the page, path in that tree).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from ..geometry import Rect
from .cells import EPS, Cell, reading_order

Point = tuple[float, float]
Path = tuple[str, ...]  # how to walk a tree to a node: ("a", "b", ...)
Where = tuple[int, Path]  # (inset index, or -1 for the page's own tree; path in that tree)


@dataclass(frozen=True)
class Shape:
    """A panel's gutter-free outline in 0..1 live-area coordinates."""

    points: tuple[Point, ...]
    cut_edges: tuple[bool, ...]   # edge i (points[i] -> points[i+1]) came from a cut
    path: Path                    # where it is in its tree
    inset: int = -1               # index in "insets", or -1 for the page's own tree

    @property
    def bbox(self) -> Cell:
        xs, ys = [p[0] for p in self.points], [p[1] for p in self.points]
        return Cell(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def empty() -> dict:
    """A blank manual layout: one panel filling the live area."""
    return {"kind": "manual", "tree": {}, "insets": [], "inset_gap": True}


# ---------- polygon helpers ----------
def _side(p1: Point, p2: Point, q: Point) -> float:
    return (p2[0] - p1[0]) * (q[1] - p1[1]) - (p2[1] - p1[1]) * (q[0] - p1[0])


def _intersect(p: Point, q: Point, p1: Point, p2: Point) -> Point:
    sp, sq = _side(p1, p2, p), _side(p1, p2, q)
    t = sp / (sp - sq)
    return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t


def _clip(points: Sequence[Point], flags: Sequence[bool], p1: Point, p2: Point, keep: int):
    """
    The part of a convex polygon on one side of the line p1-p2 (keep=+1 or -1).

    Edges keep their "made by a cut" flag; the new edge along the line is a cut edge.
    """
    out_p: list[Point] = []
    out_f: list[bool] = []
    n = len(points)
    for i in range(n):
        p, q, f = points[i], points[(i + 1) % n], flags[i]
        p_in = keep * _side(p1, p2, p) >= -1e-12
        q_in = keep * _side(p1, p2, q) >= -1e-12
        if p_in:
            out_p.append(p); out_f.append(f)
            if not q_in:
                out_p.append(_intersect(p, q, p1, p2)); out_f.append(True)  # runs along the cut
        elif q_in:
            out_p.append(_intersect(p, q, p1, p2)); out_f.append(f)
    return _tidy(out_p, out_f)


def _tidy(points: list[Point], flags: list[bool]):
    """Drop repeated points (a cut through a corner makes them)."""
    pts, fl = [], []
    for p, f in zip(points, flags):
        if pts and math.dist(p, pts[-1]) < 1e-9:
            fl[-1] = f  # the zero-length edge goes; the next edge starts here
            continue
        pts.append(p); fl.append(f)
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) < 1e-9:
        pts.pop(); fl.pop()
    return pts, fl


def _area(points: Sequence[Point]) -> float:
    return sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1]
               for i in range(len(points))) / 2


def contains(points: Sequence[Point], q: Point) -> bool:
    """Point in a convex polygon (either winding)."""
    sign = 0
    for i in range(len(points)):
        s = _side(points[i], points[(i + 1) % len(points)], q)
        if abs(s) < 1e-12:
            continue
        if sign == 0:
            sign = 1 if s > 0 else -1
        elif (s > 0) != (sign > 0):
            return False
    return True


# ---------- the trees ----------
SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


def insets(layout: dict) -> list[dict]:
    """The layout's insets as {"rect": [x, y, w, h], "tree": {...}} (early prototypes stored bare rects)."""
    return [i if isinstance(i, dict) else {"rect": list(i), "tree": {}} for i in layout.get("insets", [])]


def _to_page(rect, pt: Point) -> Point:
    x, y, w, h = rect
    return x + pt[0] * w, y + pt[1] * h


def _to_local(rect, pt: Point) -> Point:
    x, y, w, h = rect
    return (pt[0] - x) / w, (pt[1] - y) / h


def _walk(node: dict, points, flags, path: Path, out: list, inset: int) -> None:
    if not node.get("cut"):
        out.append(Shape(tuple(points), tuple(flags), path, inset))
        return
    x1, y1, x2, y2 = node["cut"]
    for key, keep in (("a", 1), ("b", -1)):
        pts, fl = _clip(points, flags, (x1, y1), (x2, y2), keep)
        if len(pts) >= 3 and abs(_area(pts)) > 1e-9:
            _walk(node.get(key, {}), pts, fl, path + (key,), out, inset)


def _tree_shapes(tree: dict, inset: int) -> list[Shape]:
    out: list[Shape] = []
    _walk(tree, list(SQUARE), [False] * 4, (), out, inset)
    return out


def shapes(layout: dict, local: bool = False) -> list[Shape]:
    """
    Every panel, gutter-free, in 0..1 live-area coordinates: the page's own
    panels, then each inset's. With ``local``, inset panels stay in their
    inset's own coordinates.
    """
    out = _tree_shapes(layout.get("tree", {}), -1)
    for i, ins in enumerate(insets(layout)):
        for s in _tree_shapes(ins["tree"], i):
            pts = s.points if local else tuple(_to_page(ins["rect"], p) for p in s.points)
            out.append(Shape(pts, s.cut_edges, s.path, i))
    return out


def _tree(layout: dict, inset: int) -> dict:
    return layout["tree"] if inset < 0 else layout["insets"][inset]["tree"]


def _node(tree: dict, path: Path) -> dict:
    for key in path:
        tree = tree[key]
    return tree


def _copy(layout: dict) -> dict:
    import json
    new = json.loads(json.dumps(layout))
    new["insets"] = insets(new)
    new.setdefault("tree", {})
    return new


def inset_at(layout: dict, q: Point) -> int:
    """The topmost inset under q, or -1."""
    for i in reversed(range(len(insets(layout)))):
        x, y, w, h = insets(layout)[i]["rect"]
        if x <= q[0] <= x + w and y <= q[1] <= y + h:
            return i
    return -1


def leaf_at(layout: dict, q: Point) -> Optional[Shape]:
    """The panel under q, in page coordinates. Insets come first: they're on top."""
    i = inset_at(layout, q)
    for s in shapes(layout):
        if s.inset == i and contains(s.points, q):
            return s
    return None


def cut(layout: dict, p1: Point, p2: Point) -> dict:
    """
    Cut the panel under the middle of p1-p2 along the line through them
    (page coordinates). Raises ValueError when the line misses that panel or
    would only shave off a sliver.
    """
    if math.dist(p1, p2) < 1e-6:
        raise ValueError("the cut is too short")
    mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    leaf = leaf_at(layout, mid)
    if leaf is None:
        raise ValueError("start the cut over a panel")
    halves = [_clip(leaf.points, leaf.cut_edges, p1, p2, k)[0] for k in (1, -1)]
    total = abs(_area(leaf.points))
    if any(len(h) < 3 or abs(_area(h)) < total * 0.02 for h in halves):
        raise ValueError("that cut doesn't split the panel")
    new = _copy(layout)
    if leaf.inset >= 0:  # inset cuts live in the inset's own coordinates, so they move with it
        rect = new["insets"][leaf.inset]["rect"]
        p1, p2 = _to_local(rect, p1), _to_local(rect, p2)
    node = _node(_tree(new, leaf.inset), leaf.path)
    node.clear()
    node.update({"cut": [round(v, 6) for v in (*p1, *p2)], "a": {}, "b": {}})
    return new


def centred(points: Sequence[Point], p1: Point, p2: Point) -> tuple[Point, Point]:
    """
    The same line moved (keeping its angle) to the middle of a panel: halfway
    between the panel's two extremes measured across the line, like Maya's
    edge-loop centre snap.
    """
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    proj = [x * nx + y * ny for x, y in points]
    shift = (min(proj) + max(proj)) / 2 - (p1[0] * nx + p1[1] * ny)
    return (p1[0] + nx * shift, p1[1] + ny * shift), (p2[0] + nx * shift, p2[1] + ny * shift)


def crossing(points: Sequence[Point], p1: Point, p2: Point) -> Optional[tuple[Point, Point]]:
    """Where the line through p1 and p2 crosses a convex polygon (for drawing a cut before it's made)."""
    hits = []
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        sp, sq = _side(p1, p2, p), _side(p1, p2, q)
        if abs(sp) < 1e-12:
            hits.append(p)
        elif sp * sq < 0:
            hits.append(_intersect(p, q, p1, p2))
    return (hits[0], hits[-1]) if len(hits) >= 2 else None


def cut_segments(layout: dict) -> list[tuple[Where, Point, Point]]:
    """Each cut as the segment you see on the page: (where, start, end), page coordinates."""
    out = []

    def walk(node, points, flags, path, inset, rect):
        if not node.get("cut"):
            return
        x1, y1, x2, y2 = node["cut"]
        span = crossing(points, (x1, y1), (x2, y2))
        if span:
            a, b = span
            out.append(((inset, path), _to_page(rect, a) if rect else a, _to_page(rect, b) if rect else b))
        for key, keep in (("a", 1), ("b", -1)):
            pts, fl = _clip(points, flags, (x1, y1), (x2, y2), keep)
            if len(pts) >= 3:
                walk(node.get(key, {}), pts, fl, path + (key,), inset, rect)

    walk(layout.get("tree", {}), list(SQUARE), [False] * 4, (), -1, None)
    for i, ins in enumerate(insets(layout)):
        walk(ins["tree"], list(SQUARE), [False] * 4, (), i, ins["rect"])
    return out


def merge(layout: dict, where: Where) -> dict:
    """Undo the cut at ``where``, and every cut made inside its two halves."""
    new = _copy(layout)
    _node(_tree(new, where[0]), where[1]).clear()
    return new


def slide(layout: dict, where: Where, dx: float, dy: float) -> dict:
    """
    Move a cut sideways (parallel to itself) by the part of (dx, dy), in page
    coordinates, that's square to it. Refused when it would lose a panel.
    """
    new = _copy(layout)
    node = _node(_tree(new, where[0]), where[1])
    x1, y1, x2, y2 = node["cut"]
    if where[0] >= 0:  # into the inset's own coordinates
        _x, _y, w, h = new["insets"][where[0]]["rect"]
        dx, dy = dx / w, dy / h
    ux, uy = x2 - x1, y2 - y1
    length = math.hypot(ux, uy)
    nx, ny = -uy / length, ux / length
    d = dx * nx + dy * ny
    node["cut"] = [round(v, 6) for v in (x1 + nx * d, y1 + ny * d, x2 + nx * d, y2 + ny * d)]
    if len(shapes(new)) != len(shapes(layout)) or any(abs(_area(s.points)) < 1e-4 for s in shapes(new)):
        raise ValueError("that would squeeze a panel out")
    return new


def add_inset(layout: dict, x: float, y: float, w: float, h: float) -> dict:
    new = _copy(layout)
    new["insets"].append({"rect": [round(v, 6) for v in (x, y, w, h)], "tree": {}})
    return new


def set_inset_rect(layout: dict, index: int, x: float, y: float, w: float, h: float) -> dict:
    """Move or resize an inset; its own cuts come along, since they're stored relative to it."""
    if w <= 0 or h <= 0:
        raise ValueError("an inset needs a size")
    new = _copy(layout)
    new["insets"][index]["rect"] = [round(v, 6) for v in (x, y, w, h)]
    return new


def remove_inset(layout: dict, index: int) -> dict:
    new = _copy(layout)
    del new["insets"][index]
    return new


def inset_rects_mm(layout: dict, live: Rect) -> list[Rect]:
    """Each inset's outline in canvas mm (for the gap drawn behind it)."""
    return [Rect(live.x + x * live.w, live.y + y * live.h, w * live.w, h * live.h)
            for x, y, w, h in (i["rect"] for i in insets(layout))]


# ---------- from rectangles ----------
def from_cells(cells: Sequence[Cell]) -> Optional[dict]:
    """
    The same layout as a cut tree, so a preset or random layout can be
    edited by hand. Works when the layout can be made with straight cuts
    right across (almost every comic layout); returns None for the rare
    pinwheel-style ones that can't.
    """
    def split(group: list[Cell], box: Cell) -> Optional[dict]:
        if len(group) == 1:
            return {}
        for vertical in (False, True):
            edges = sorted({round(c.x if vertical else c.y, 6) for c in group} - {round(box.x if vertical else box.y, 6)})
            for e in edges:
                first = [c for c in group if (c.right if vertical else c.bottom) <= e + EPS]
                second = [c for c in group if (c.x if vertical else c.y) >= e - EPS]
                if first and second and len(first) + len(second) == len(group):
                    if vertical:
                        line = [e, 0.0, e, 1.0]
                        boxes = (Cell(box.x, box.y, e - box.x, box.h), Cell(e, box.y, box.right - e, box.h))
                    else:
                        line = [0.0, e, 1.0, e]
                        boxes = (Cell(box.x, box.y, box.w, e - box.y), Cell(box.x, e, box.w, box.bottom - e))
                    # Which half is "a" depends on the line's direction, so test it instead of assuming.
                    a_side = _side((line[0], line[1]), (line[2], line[3]),
                                   (first[0].x + first[0].w / 2, first[0].y + first[0].h / 2)) > 0
                    sub1, sub2 = split(first, boxes[0]), split(second, boxes[1])
                    if sub1 is None or sub2 is None:
                        return None
                    return {"cut": line, "a": sub1 if a_side else sub2, "b": sub2 if a_side else sub1}
        return None

    if not cells:
        return None
    tree = split(list(cells), Cell(0.0, 0.0, 1.0, 1.0))
    return None if tree is None else {"kind": "manual", "tree": tree, "insets": [], "inset_gap": True}


# ---------- to millimetres ----------
def _inset_polygon(points: Sequence[Point], offsets: Sequence[float]) -> list[Point]:
    """
    Move each edge of a convex polygon inwards by its own distance. Raises
    ValueError when the gutter swallows it.

    Done as clipping: keep the part of the polygon on the inside of every
    moved edge. Simply re-intersecting neighbouring edges goes wrong when a
    cut passes close to a corner: the tiny edge left there should vanish,
    and re-intersecting pushes a point out past the panel instead.
    """
    ccw = _area(points) > 0
    out = list(points)
    flags = [False] * len(out)
    n = len(points)
    for i in range(n):
        d = offsets[i]
        if d <= 0:
            continue
        p, q = points[i], points[(i + 1) % n]
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dy)
        # Inward normal: with a positive shoelace area the inside is to the left of each edge.
        nx, ny = (-dy / length, dx / length) if ccw else (dy / length, -dx / length)
        a, b = (p[0] + nx * d, p[1] + ny * d), (q[0] + nx * d, q[1] + ny * d)
        keep = 1 if _side(a, b, (a[0] + nx, a[1] + ny)) > 0 else -1
        out, flags = _clip(out, flags, a, b, keep)
        if len(out) < 3:
            break
    if len(out) < 3 or abs(_area(out)) < 1.0:  # under 1 mm²
        raise ValueError("the gutter is wider than a panel")
    return out


@dataclass(frozen=True)
class MmPanel:
    cell: Cell                    # gutter-free bounding box, 0..1 (what cpb:cell stores)
    points: tuple[Point, ...]     # final outline in canvas mm, gutter applied
    inset: int                    # which inset it belongs to, or -1

    @property
    def on_top(self) -> bool:
        return self.inset >= 0


def to_mm(layout: dict, live: Rect, gutter: float, reading: str = "ltr") -> list[MmPanel]:
    """Panels in canvas mm, gutters applied, in reading order."""
    out = []
    for s in shapes(layout):
        pts = [(live.x + x * live.w, live.y + y * live.h) for x, y in s.points]
        # Edges made by a cut move in by half the gutter; outer edges (the
        # live area's, or an inset's own border) stay where they are.
        mm = _inset_polygon(pts, [gutter / 2 if f else 0.0 for f in s.cut_edges])
        # Clockwise on screen (y down), starting top-left, so files read the same every save.
        if _area(mm) < 0:
            mm = mm[::-1]
        start = min(range(len(mm)), key=lambda i: (round(mm[i][1], 6), mm[i][0]))
        mm = mm[start:] + mm[:start]
        out.append(MmPanel(s.bbox, tuple((round(x, 4), round(y, 4)) for x, y in mm), s.inset))
    order = reading_order([p.cell for p in out], reading)
    remaining = list(out)
    ordered = []
    for c in order:
        i = next(i for i, p in enumerate(remaining) if p.cell == c)
        ordered.append(remaining.pop(i))
    return ordered
