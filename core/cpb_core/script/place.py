"""
A script page's lines as balloons on a project page.

The point is to save typing and sorting, not to letter the page: every line
lands in the right panel, in reading order, already holding its words, in
the font of its role, with its tail pointing down. Placing them around the
art and aiming the tails is still yours to do on the Balloons screen.

Inside a panel, balloons flow like words in a paragraph: along the top from
the reading side (left, or right for manga), then a new row below. Captions
take the same flow, so a caption that opens a panel ends up in its corner.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from ..balloons import Balloon, BalloonFont, Tail, approx_measure, fit_balloon
from ..balloons.text import PADDING
from ..units import MM_PER_PT
from ..geometry import Rect
from .reader import Script, ScriptLine, ScriptPage

PAD = 2.5      # mm between a balloon and its panel's edge
GAP = 2.0      # mm between balloons
TAIL = 9.0     # mm a new tail reaches below its balloon

ROLE_FOR_KIND = {"caption": "caption", "whisper": "whisper"}

FontFor = Callable[[str], BalloonFont]
Fit = Callable[[Balloon], Balloon]


def _rough_fit(b: Balloon) -> Balloon:
    return fit_balloon(b, approx_measure(b.font.size_pt))


@dataclass
class PlacedPage:
    balloons: list[Balloon] = field(default_factory=list)
    sfx: list[ScriptLine] = field(default_factory=list)  # listed for you, not made into balloons
    warnings: list[str] = field(default_factory=list)


def regions(page, panel_count: int) -> list[Rect]:
    """
    Where each script panel's lines go: the page's panels in reading order,
    or for a drawn page (no panels to read), bands down the live area.
    A slanted panel gives its bounding box; balloons may need a nudge inside it.
    """
    panels = sorted(page.panels(), key=lambda p: p.index)
    if panels:
        return [p.rect for p in panels]
    live = page.geometry().live
    n = max(1, panel_count)
    h = live.h / n
    return [Rect(live.x, live.y + i * h, live.w, h) for i in range(n)]


def balloon_for(line: ScriptLine, number: int, font_for: FontFor) -> Optional[Balloon]:
    """The balloon a line becomes (not placed yet), or None for a sound effect."""
    if line.kind == "sfx":
        return None
    kind = "caption" if line.kind == "floating" else line.kind
    role = ROLE_FOR_KIND.get(line.kind, "dialogue")
    b = Balloon(number=number, kind=kind, text=line.text, role=role, font=font_for(role))
    if line.kind == "floating":
        # "No bubble": the words float over the art, so no box and no outline.
        b = replace(b, fill=None, stroke_width=0.0)
    return b


def balloons_for_page(script_page: ScriptPage, page, *, font_for: FontFor, fit: Fit = _rough_fit,
                      start_number: int = 1, reading: Optional[str] = None,
                      label: Optional[str] = None) -> PlacedPage:
    """Lay one script page's lines out on a core Page. Balloon numbers start at start_number."""
    out = PlacedPage()
    name = label or f"Page {script_page.number}"
    reading = reading or getattr(page, "reading", "ltr")
    spots = regions(page, len(script_page.panels))
    if len(script_page.panels) > len(spots):
        extra = len(script_page.panels) - len(spots)
        out.warnings.append(f"{name}: the script has {len(script_page.panels)} panels and the page {len(spots)}, "
                            f"so the lines of the last {extra} went into panel {len(spots)}.")
    number = start_number
    queued: list[list[Balloon]] = [[] for _ in spots]
    for i, panel in enumerate(script_page.panels):
        for line in panel.lines:
            b = balloon_for(line, number, font_for)
            if b is None:
                out.sfx.append(line)
                continue
            queued[min(i, len(spots) - 1)].append(b)
            number += 1
    for i, (spot, balloons) in enumerate(zip(spots, queued)):
        placed, fits = _flow(balloons, spot, reading, fit)
        out.balloons.extend(placed)
        if not fits:
            out.warnings.append(f"{name}, panel {i + 1}: the lines don't all fit, so some balloons overlap.")
    return out


def _flow(balloons: list[Balloon], r: Rect, reading: str, fit: Fit) -> tuple[list[Balloon], bool]:
    """Place balloons row by row inside r. False if they ran out of room."""
    inner_w = max(4.0, r.w - 2 * PAD)
    tail_len = max(3.0, min(TAIL, r.h * 0.15))
    out: list[Balloon] = []
    fits = True
    x, y, row_h = 0.0, r.y + PAD, 0.0   # x: distance from the reading-side edge
    for b in balloons:
        b = fit(b)
        if 2 * b.rx > inner_w:
            # Wider than the panel: keep the panel's width and let the text wrap to it.
            b = fit(replace(b, auto_size=False, rx=inner_w / 2))
            b = replace(b, ry=max(b.ry, _rows_height(b) / 2))
        w, h = 2 * b.rx, 2 * b.ry
        has_tail = b.kind != "caption"
        if x > 0 and x + w > inner_w:
            x, y, row_h = 0.0, y + row_h + GAP, 0.0
        if y + h > r.y + r.h - PAD:
            fits = False
        left = r.x + PAD + x if reading != "rtl" else r.x + r.w - PAD - x - w
        cx, cy = round(left + b.rx, 3), round(y + b.ry, 3)
        tail = None
        if has_tail:
            # Down, and a little toward the panel's middle, where the speaker usually is.
            lean = -1 if cx > r.x + r.w / 2 else 1
            tip_x = cx + lean * min(b.rx * 0.3, 4.0)
            tip_y = max(min(cy + b.ry + tail_len, r.y + r.h - 1.0), cy + b.ry + 2.0)
            tail = Tail(tip_x=round(tip_x, 3), tip_y=round(tip_y, 3))
        out.append(replace(b, cx=cx, cy=cy, tail=tail))
        x += w + GAP
        row_h = max(row_h, h + (tail_len if has_tail else 0.0))
    return out, fits


def _rows_height(b: Balloon) -> float:
    """The height the wrapped text needs, plus padding (for a body sized by hand)."""
    n = len(b.lines or ()) or 1
    size = b.font.size_pt * MM_PER_PT
    text_h = size * b.font.cap_ratio + size * b.font.leading * (n - 1)
    return text_h * (1.0 if b.kind == "caption" else 1.42) + 2 * PADDING[b.kind]


# ---------- the whole script onto the project ----------

@dataclass
class ScriptReport:
    pages: list[int] = field(default_factory=list)          # project pages that got balloons
    balloons: int = 0
    skipped: list[int] = field(default_factory=list)        # already had balloons
    missing: list[int] = field(default_factory=list)        # script pages with no project page
    sfx: dict[int, list[ScriptLine]] = field(default_factory=dict)  # project page -> its sound effects
    warnings: list[str] = field(default_factory=list)


def apply_script(project, script: Script, *, first_page: int = 1, not_speakers: frozenset = frozenset(),
                 existing: str = "skip", font_for: Optional[FontFor] = None, fit: Fit = _rough_fit,
                 pages: Optional[set] = None) -> ScriptReport:
    """
    Put the script's balloons on the project's pages and save them.

    Script page N goes on project page N + first_page - 1. A page that
    already has balloons is skipped (existing="skip", so running this twice
    doesn't double them) or gets the new ones after its own (existing="add").
    pages limits it to some project pages. Only each page's Letters layer is
    rewritten.
    """
    from ..svg import read_page
    if existing not in ("skip", "add"):
        raise ValueError("existing must be 'skip' or 'add'")
    if font_for is None:
        font_for = lambda role: project.balloon_font(role) or BalloonFont()  # noqa: E731
    numbers = {e.number for e in project.pages}
    report = ScriptReport()
    for sp in script.without(set(not_speakers)).pages:
        target = sp.number + first_page - 1
        if pages is not None and target not in pages:
            continue
        if target not in numbers:
            if sp.lines():
                report.missing.append(sp.number)
            continue
        if not any(ln.kind != "sfx" for ln in sp.lines()):
            sfx = [ln for ln in sp.lines() if ln.kind == "sfx"]
            if sfx:
                report.sfx[target] = sfx
            continue
        doc = read_page(project.page_path(target))
        have = list(doc.page.balloons or ())
        if have and existing == "skip":
            report.skipped.append(target)
            continue
        start = max((b.number for b in have), default=0) + 1
        placed = balloons_for_page(sp, doc.page, font_for=font_for, fit=fit, start_number=start,
                                   label=f"page_{target:02d}")
        project.save_balloons(target, have + placed.balloons)
        report.pages.append(target)
        report.balloons += len(placed.balloons)
        if placed.sfx:
            report.sfx[target] = placed.sfx
        report.warnings.extend(placed.warnings)
    return report
