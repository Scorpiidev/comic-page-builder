"""
layout_generator.py — BSP panel layout randomizer

Cut modes:
  "auto"       — always cut the longer axis (most balanced)
  "horizontal" — strips only (horizontal cuts)
  "vertical"   — columns only (vertical cuts)
  "random"     — pure random axis each split

The gutter_mm parameter controls the space BETWEEN panels, which is
separate from line_strength (the border thickness). Default: 3mm.
"""

import random
from dataclasses import dataclass, field
from typing import Optional

MAX_PANELS   = 8
MIN_PANELS   = 1
MIN_PANEL_MM_W = 30.0
MIN_PANEL_MM_H = 40.0
DEFAULT_GUTTER_MM = 3.0


@dataclass
class _Node:
    x: float; y: float; w: float; h: float
    left:  Optional["_Node"] = field(default=None, repr=False)
    right: Optional["_Node"] = field(default=None, repr=False)
    split_axis: Optional[str] = None
    split_pos:  float = 0.0

    def is_leaf(self) -> bool:
        return self.left is None and self.right is None

    def leaves(self) -> list:
        if self.is_leaf():
            return [self]
        result = []
        if self.left:  result.extend(self.left.leaves())
        if self.right: result.extend(self.right.leaves())
        return result


def _can_split_h(node, gutter, min_h):
    return node.h - gutter >= min_h * 2

def _can_split_v(node, gutter, min_w):
    return node.w - gutter >= min_w * 2


def _split(node, axis, gutter, min_w, min_h, rng):
    if axis == "h":
        if not _can_split_h(node, gutter, min_h):
            return False
        lo = node.y + min_h
        hi = node.y + node.h - gutter - min_h
        if lo >= hi:
            return False
        cut = rng.uniform(lo, hi)
        node.split_axis = "h"
        node.split_pos  = cut
        node.left  = _Node(node.x, node.y,          node.w, cut - node.y)
        node.right = _Node(node.x, cut + gutter,     node.w, node.y + node.h - cut - gutter)
        return True
    else:  # "v"
        if not _can_split_v(node, gutter, min_w):
            return False
        lo = node.x + min_w
        hi = node.x + node.w - gutter - min_w
        if lo >= hi:
            return False
        cut = rng.uniform(lo, hi)
        node.split_axis = "v"
        node.split_pos  = cut
        node.left  = _Node(node.x,          node.y, cut - node.x,              node.h)
        node.right = _Node(cut + gutter,     node.y, node.x + node.w - cut - gutter, node.h)
        return True


def _choose_axis(node, mode, rng, gutter_h, gutter_w, min_w, min_h):
    # Must use the same per-axis gutters as _split(), or we can pick an
    # axis that _split() then rejects.
    can_h = _can_split_h(node, gutter_h, min_h)
    can_v = _can_split_v(node, gutter_w, min_w)
    if not can_h and not can_v: return ""
    if can_h and not can_v:     return "h"
    if can_v and not can_h:     return "v"
    if mode == "auto":          return "h" if node.h >= node.w else "v"
    elif mode == "horizontal":  return "h"
    elif mode == "vertical":    return "v"
    else:                       return rng.choice(["h", "v"])


def generate_layout(
    n_panels:      int,
    binding_w_mm:  float,
    binding_h_mm:  float,
    gutter_mm:     float = DEFAULT_GUTTER_MM,
    cut_mode:      str   = "auto",
    seed:          Optional[int] = None,
) -> list:
    """
    Generate a random BSP panel layout.
    Returns normalised [0,1] rect dicts: {x, y, width, height}.

    gutter_mm is the space between panels (default 3mm).
    This is SEPARATE from line_strength (the border width).

    May return fewer than n_panels rects when the minimum panel size
    doesn't leave room for more; callers should use len() of the result.
    """
    n_panels = max(MIN_PANELS, min(MAX_PANELS, n_panels))
    rng      = random.Random(seed)

    # Normalize to [0,1] space. Horizontal cuts eat height, vertical cuts
    # eat width, so each axis gets its own normalised gutter.
    min_w    = MIN_PANEL_MM_W / binding_w_mm if binding_w_mm > 0 else 0.10
    min_h    = MIN_PANEL_MM_H / binding_h_mm if binding_h_mm > 0 else 0.13
    gutter_w = gutter_mm / binding_w_mm if binding_w_mm > 0 else 0.014
    gutter_h = gutter_mm / binding_h_mm if binding_h_mm > 0 else 0.010

    root   = _Node(0.0, 0.0, 1.0, 1.0)
    leaves = [root]
    stuck  = set()   # ids of leaves whose split failed; never retried

    while len(leaves) < n_panels:
        splittable = [
            l for l in leaves
            if id(l) not in stuck
            and (_can_split_h(l, gutter_h, min_h) or _can_split_v(l, gutter_w, min_w))
        ]
        if not splittable:
            break

        target = max(splittable, key=lambda l: l.w * l.h)
        axis   = _choose_axis(target, cut_mode, rng, gutter_h, gutter_w, min_w, min_h)
        g      = gutter_h if axis == "h" else gutter_w
        if axis and _split(target, axis, g, min_w, min_h, rng):
            leaves = root.leaves()
        else:
            # Edge case (e.g. exactly at the size limit): move on to the
            # next-largest leaf instead of burning a panel.
            stuck.add(id(target))

    return [
        {
            "x":      round(leaf.x, 6),
            "y":      round(leaf.y, 6),
            "width":  round(leaf.w, 6),
            "height": round(leaf.h, 6),
        }
        for leaf in root.leaves()
    ]


def make_layout_dict(rects: list, label: str = "Random") -> dict:
    return {
        "path":     None,
        "name":     label,
        "frames":   len(rects),
        "is_title": False,
        "rects":    rects,
    }


def save_layout_json(rects: list, name: str, folder: str) -> str:
    """
    Save a list of normalised rects as a layout JSON file.
    Returns the full path of the saved file.
    """
    import json, os, re
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[^\w\s\-]', '', name).strip().replace(' ', '_')
    path = os.path.join(folder, f"{safe}.json")
    data = {"layout": [{"type": "rect", "data": r} for r in rects]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    return path
