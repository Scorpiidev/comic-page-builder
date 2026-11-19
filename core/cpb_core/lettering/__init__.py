"""
Lettering: font metrics, the print size advisor, and the calibration sheet.

    fonts.py        read font files (TTF, OTF, TTC) with the standard library
    advisor.py      cap height maths, recommended sizes, verdicts, presets
    calibration.py  the printable test sheet that settles a project's sizes
"""

from .advisor import (MIN_CAP_MM, ROLES, TARGETS, LetteringPreset, cap_height_mm, recommend_pt,
                      verdict, working_pt)
from .calibration import CalibrationSheet, FontChoice, Sample, build_sheet, sheet_svg, sizes_around
from .fonts import FontInfo, ScanResult, default_font_dirs, read_font_file, scan_fonts

__all__ = [
    "MIN_CAP_MM", "ROLES", "TARGETS", "LetteringPreset", "cap_height_mm", "recommend_pt", "verdict", "working_pt",
    "CalibrationSheet", "FontChoice", "Sample", "build_sheet", "sheet_svg", "sizes_around",
    "FontInfo", "ScanResult", "default_font_dirs", "read_font_file", "scan_fonts",
]
