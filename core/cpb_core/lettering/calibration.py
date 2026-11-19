"""
The calibration sheet: a printed page of sample balloons at nearby sizes.

The size advisor's targets are starting points. Printers, papers and fonts
differ, so the real answer comes from printing this sheet at 100%, looking
at it at arm's length, and picking the sample that reads comfortably. Each
sample has a code ("A4", "B2"...) so the hub can turn that choice into the
project's preset.

``build_sheet`` lays the sheet out in millimetres. The hub renders it to PDF
with the real fonts (exact sizes, fonts embedded); ``sheet_svg`` is a quick
preview whose text widths are only estimated.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..svg.ns import num
from .advisor import TARGETS, cap_height_mm, recommend_pt

PAPERS = {"A4": (210.0, 297.0), "Letter": (215.9, 279.4)}
SAMPLE_TEXT = "IS THIS EASY\nTO READ?"
MAX_FONTS = 3        # what fits on one page with six samples each
STEPS = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0)  # pt around the recommendation
MARGIN = 15.0
HEADER = 46.0
CELL_H = 30.0
LABEL_H = 9.0
BLOCK_GAP = 6.0


@dataclass(frozen=True)
class FontChoice:
    family: str
    style: str
    cap_ratio: float
    ps_name: str = ""


@dataclass(frozen=True)
class Sample:
    code: str       # "A4": font A, fourth sample
    font: FontChoice
    size_pt: float
    cap_mm: float
    x: float        # cell rectangle, mm from the top-left of the paper
    y: float
    w: float
    h: float
    text: str = SAMPLE_TEXT


@dataclass(frozen=True)
class CalibrationSheet:
    title: str
    role: str
    paper: str
    width: float
    height: float
    fonts: tuple[tuple[str, FontChoice, float], ...]  # (letter, font, block top y)
    samples: tuple[Sample, ...]
    ruler: tuple[float, float, float]  # x, y, length in mm (always 100)

    def sample(self, code: str) -> Sample:
        for s in self.samples:
            if s.code.upper() == code.strip().upper():
                return s
        raise KeyError(f"there's no sample {code!r} on this sheet")


def sizes_around(recommended: float, minimum: float = 4.0) -> list[float]:
    """Six sizes around the recommendation, in half points, never below ``minimum``."""
    sizes = []
    for step in STEPS:
        s = max(minimum, recommended + step)
        if s not in sizes:
            sizes.append(s)
    return sizes


def build_sheet(fonts: list[FontChoice], *, role: str = "dialogue", paper: str = "A4", title: str = "") -> CalibrationSheet:
    if not fonts:
        raise ValueError("pick at least one font for the sheet")
    if len(fonts) > MAX_FONTS:
        raise ValueError(f"a sheet fits {MAX_FONTS} fonts; make another sheet for the rest")
    if role not in TARGETS:
        raise ValueError(f"role must be one of: {', '.join(TARGETS)}")
    try:
        w, h = PAPERS[paper]
    except KeyError:
        raise ValueError(f"paper must be one of: {', '.join(PAPERS)}") from None
    cols = 3
    cell_w = (w - 2 * MARGIN) / cols
    y = MARGIN + HEADER
    blocks, samples = [], []
    for fi, font in enumerate(fonts):
        letter = "ABC"[fi]
        blocks.append((letter, font, y))
        sizes = sizes_around(recommend_pt(font.cap_ratio, role))
        for i, size in enumerate(sizes):
            row, col = divmod(i, cols)
            samples.append(Sample(code=f"{letter}{i + 1}", font=font, size_pt=size,
                                  cap_mm=round(cap_height_mm(size, font.cap_ratio), 2),
                                  x=MARGIN + col * cell_w, y=y + LABEL_H + row * CELL_H, w=cell_w, h=CELL_H))
        rows = (len(sizes) + cols - 1) // cols
        y += LABEL_H + rows * CELL_H + BLOCK_GAP
    if y - BLOCK_GAP > h - MARGIN:
        raise ValueError("the samples don't fit on this paper")
    return CalibrationSheet(title=title or "Lettering calibration", role=role, paper=paper, width=w, height=h,
                            fonts=tuple(blocks), samples=tuple(samples), ruler=(MARGIN, MARGIN + 30.0, 100.0))


INSTRUCTIONS = ("Print at 100% (\"Actual size\", not \"Fit to page\"). The bar below must measure exactly 100 mm. "
                "Hold the page at arm's length and pick the smallest sample that reads comfortably, "
                "then type its code in the hub.")


def _style_attrs(style: str) -> str:
    s = style.lower()
    weight = "700" if "bold" in s or "black" in s or "heavy" in s else "400"
    italic = ' font-style="italic"' if "italic" in s or "oblique" in s else ""
    return f'font-weight="{weight}"{italic}'


def sheet_svg(sheet: CalibrationSheet) -> str:
    """A preview of the sheet as SVG (mm units). Text widths are estimated; print the hub's PDF."""
    W, H = sheet.width, sheet.height
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{num(W)}mm" height="{num(H)}mm" viewBox="0 0 {num(W)} {num(H)}">',
           f'<rect width="{num(W)}" height="{num(H)}" fill="#ffffff"/>',
           f'<text x="{num(MARGIN)}" y="{num(MARGIN + 6)}" font-family="sans-serif" font-size="5.5" fill="#1b1b1b">{_esc(sheet.title)}</text>',
           f'<text x="{num(MARGIN)}" y="{num(MARGIN + 13)}" font-family="sans-serif" font-size="2.8" fill="#555555">Role: {sheet.role} · {sheet.paper}</text>']
    words, line, ly = INSTRUCTIONS.split(), "", MARGIN + 19
    for w_ in words:  # rough wrap at ~95 characters
        if len(line) + len(w_) > 95:
            out.append(f'<text x="{num(MARGIN)}" y="{num(ly)}" font-family="sans-serif" font-size="2.8" fill="#555555">{_esc(line)}</text>')
            line, ly = w_, ly + 4
        else:
            line = f"{line} {w_}".strip()
    out.append(f'<text x="{num(MARGIN)}" y="{num(ly)}" font-family="sans-serif" font-size="2.8" fill="#555555">{_esc(line)}</text>')
    rx, ry, rl = sheet.ruler
    out.append(f'<rect x="{num(rx)}" y="{num(ry)}" width="{num(rl)}" height="2.5" fill="#1b1b1b"/>')
    for i in range(11):
        out.append(f'<rect x="{num(rx + i * 10 - 0.15)}" y="{num(ry + 2.5)}" width="0.3" height="{2 if i % 5 == 0 else 1.2}" fill="#1b1b1b"/>')
    out.append(f'<text x="{num(rx + rl + 3)}" y="{num(ry + 2.4)}" font-family="sans-serif" font-size="3" fill="#1b1b1b">100 mm</text>')
    for letter, font, top in sheet.fonts:
        out.append(f'<text x="{num(MARGIN)}" y="{num(top + 6)}" font-family="sans-serif" font-size="3.6" fill="#b83c70">'
                   f'{letter} · {_esc(font.family)} {_esc(font.style)} · caps {font.cap_ratio:.2f} em</text>')
    for s in sheet.samples:
        fs = s.size_pt * 25.4 / 72
        lines = s.text.split("\n")
        est_w = max(len(l) for l in lines) * fs * 0.62
        est_h = len(lines) * fs * 1.15
        cx, cy = s.x + s.w / 2, s.y + s.h / 2 - 2
        a, b = min(s.w / 2 - 2, est_w / 1.414 + 2), min(s.h / 2 - 4, est_h / 1.414 + 1.5)
        out.append(f'<ellipse cx="{num(cx)}" cy="{num(cy)}" rx="{num(a)}" ry="{num(b)}" fill="#ffffff" stroke="#1b1b1b" stroke-width="0.3"/>')
        y0 = cy - (len(lines) - 1) * fs * 1.15 / 2 + fs * s.font.cap_ratio / 2
        tspans = "".join(f'<tspan x="{num(cx)}" y="{num(y0 + i * fs * 1.15)}">{_esc(l)}</tspan>' for i, l in enumerate(lines))
        out.append(f'<text text-anchor="middle" font-family="{_esc(s.font.family)}" {_style_attrs(s.font.style)} '
                   f'font-size="{num(fs)}" fill="#1b1b1b">{tspans}</text>')
        out.append(f'<text x="{num(s.x + 2)}" y="{num(s.y + s.h - 1.5)}" font-family="sans-serif" font-size="2.6" fill="#555555">'
                   f'{s.code} · {s.size_pt:g} pt · {s.cap_mm:.2f} mm caps</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
