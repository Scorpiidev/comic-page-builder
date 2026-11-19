"""
Render a calibration sheet to PDF with the real fonts.

QPdfWriter maps point sizes to physical size exactly and embeds the fonts,
so the printed sheet shows what the comic will look like. The layout itself
comes from cpb_core.lettering.calibration; this module only draws it.
"""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen

from cpb_core.lettering.calibration import INSTRUCTIONS, CalibrationSheet, FontChoice

RESOLUTION = 1200  # dots per inch inside the PDF; plenty for hairlines


def render_sheet_pdf(sheet: CalibrationSheet, path: str, qfont: Callable[[FontChoice, float], QFont]) -> None:
    """Write the sheet to ``path``. ``qfont(font, size_pt)`` gives the QFont for a sample."""
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QSizeF(sheet.width, sheet.height), QPageSize.Millimeter, sheet.paper))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    writer.setResolution(RESOLUTION)
    writer.setTitle(sheet.title)
    writer.setCreator("Comic Hub")
    mm = RESOLUTION / 25.4  # device units per millimetre

    p = QPainter(writer)
    p.setRenderHint(QPainter.Antialiasing)
    ink, grey, pink = QColor("#1b1b1b"), QColor("#555555"), QColor("#b83c70")

    def ui(size_pt: float, bold: bool = False) -> QFont:
        f = QFont("Segoe UI")
        f.setStyleHint(QFont.SansSerif)
        f.setPointSizeF(size_pt)
        f.setBold(bold)
        return f

    def text(x_mm, y_mm, s, font, color, w_mm=None, flags=Qt.AlignLeft | Qt.AlignTop) -> float:
        p.setFont(font)
        p.setPen(color)
        width = (w_mm or sheet.width - 2 * x_mm) * mm
        rect = p.boundingRect(QRectF(x_mm * mm, y_mm * mm, width, 1e6), flags | Qt.TextWordWrap, s)
        p.drawText(rect, flags | Qt.TextWordWrap, s)
        return rect.height() / mm

    margin = sheet.ruler[0]
    y = margin
    y += text(margin, y, sheet.title, ui(16, True), ink) + 1
    y += text(margin, y, f"Role: {sheet.role} · paper {sheet.paper} · printed at 100% this page is "
                         f"{sheet.width:g} × {sheet.height:g} mm", ui(8), grey) + 1.5
    text(margin, y, INSTRUCTIONS, ui(8), grey)

    # The 100 mm bar: if it doesn't measure 100 mm on paper, the printer scaled the page.
    rx, ry, rl = sheet.ruler
    p.fillRect(QRectF(rx * mm, ry * mm, rl * mm, 2.5 * mm), ink)
    for i in range(11):
        h = 2.0 if i % 5 == 0 else 1.2
        p.fillRect(QRectF((rx + i * 10 - 0.15) * mm, (ry + 2.5) * mm, 0.3 * mm, h * mm), ink)
    text(rx + rl + 3, ry - 0.6, "100 mm", ui(9, True), ink, w_mm=30)

    for letter, font, top in sheet.fonts:
        text(margin, top + 1.5, f"{letter} · {font.family} {font.style} · caps {font.cap_ratio:.2f} em", ui(10, True), pink)

    pen = QPen(ink)
    pen.setWidthF(0.3 * mm)
    for s in sheet.samples:
        f = qfont(s.font, s.size_pt)
        fm = QFontMetricsF(f, writer)
        max_w = (s.w - 8) * mm
        block = fm.boundingRect(QRectF(0, 0, max_w, 1e6), Qt.AlignCenter | Qt.TextWordWrap, s.text)
        # The balloon fits the text: an ellipse through the corners of the text block, plus padding.
        a = min(s.w / 2 - 2, block.width() / mm / math.sqrt(2) + 2)
        b = min(s.h / 2 - 3.5, block.height() / mm / math.sqrt(2) + 1.5)
        cx, cy = (s.x + s.w / 2) * mm, (s.y + s.h / 2 - 2) * mm
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), a * mm, b * mm)
        p.setPen(pen)
        p.setBrush(QColor("#ffffff"))
        p.drawPath(path)
        p.setFont(f)
        p.setPen(ink)
        p.drawText(QRectF(cx - block.width() / 2, cy - block.height() / 2, block.width(), block.height()),
                   Qt.AlignCenter | Qt.TextWordWrap, s.text)
        text(s.x + 2, s.y + s.h - 5, f"{s.code} · {s.size_pt:g} pt · {s.cap_mm:.2f} mm caps", ui(7), grey, w_mm=s.w - 4)
    p.end()
