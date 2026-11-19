"""
Lettering size advisor: how big text has to be to read well in print.

The rule (docs/DESIGN.md section 9): size lettering by its **cap height at
the final printed size**, never by the working canvas. Comic fonts are
usually all caps, so cap height says more about legibility than the
nominal point size: two fonts at "8 pt" can print very differently.

``cap_ratio`` is the font's cap height divided by its em size (typically
0.6-0.75). ``fonts.py`` reads it from the font file; this module is plain
arithmetic on top, so the CLI, the hub and tests all agree.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..units import MM_PER_PT

# Target cap height at print size, in mm. Starting points to calibrate with a
# test print, not gospel: the calibration sheet is how you find your own.
TARGETS = {"dialogue": 2.1, "caption": 2.0, "whisper": 1.6, "sfx": 4.5}
MIN_CAP_MM = 1.5  # below this, print lettering gets hard to read
ROLES = tuple(TARGETS)


def cap_height_mm(size_pt: float, cap_ratio: float) -> float:
    """Printed cap height for a font size, in mm."""
    return size_pt * MM_PER_PT * cap_ratio


def recommend_pt(cap_ratio: float, role: str = "dialogue") -> float:
    """The size (in pt, rounded to 0.5) whose cap height hits the role's target."""
    if role not in TARGETS:
        raise ValueError(f"role must be one of: {', '.join(ROLES)}")
    if not 0.2 <= cap_ratio <= 1.2:
        raise ValueError("a cap height ratio should be between 0.2 and 1.2 of the em")
    return round(TARGETS[role] / (MM_PER_PT * cap_ratio) * 2) / 2


def working_pt(size_pt: float, work_scale: float) -> float:
    """
    The size to type in your canvas when you draw bigger than print.

    Drawing at 2x means the page shrinks by half when printed, so the text
    has to be twice as big in the canvas.
    """
    return size_pt * work_scale


def verdict(cap_mm: float, role: str = "dialogue") -> tuple[str, str]:
    """('bad' | 'small' | 'good', a sentence for the UI)."""
    target = TARGETS[role]
    if cap_mm < MIN_CAP_MM:
        return "bad", (f"Too small for print: {cap_mm:.2f} mm cap height is below the "
                       f"{MIN_CAP_MM} mm minimum. Readers will squint.")
    if cap_mm < target - 0.15:
        return "small", f"Readable, but small for {role}. The target is about {target} mm cap height."
    return "good", f"Reads well in print ({cap_mm:.2f} mm cap height)."


@dataclass(frozen=True)
class LetteringPreset:
    """A project's chosen font and size for one text role."""

    family: str
    style: str
    size_pt: float
    cap_ratio: float
    # Illustrator and Photoshop pick fonts by PostScript name, SVG by family,
    # so both are kept (docs/DESIGN.md section 5.2).
    ps_name: str = ""

    @property
    def cap_mm(self) -> float:
        return cap_height_mm(self.size_pt, self.cap_ratio)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "LetteringPreset":
        return cls(family=data["family"], style=data.get("style", "Regular"),
                   size_pt=float(data["size_pt"]), cap_ratio=float(data["cap_ratio"]),
                   ps_name=data.get("ps_name", ""))
