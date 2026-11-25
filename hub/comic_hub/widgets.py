"""Small reusable widgets: unit-safe spin boxes, page previews, the toast."""

from __future__ import annotations

import os
import re
from dataclasses import replace

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from cpb_core.model import Page
from cpb_core.svg import page_to_svg
from cpb_core.units import MM_PER_UNIT

from . import icons, theme

UNIT_DECIMALS = {"mm": 1, "cm": 2, "in": 3}


class UnitSpinBox(QDoubleSpinBox):
    """
    Shows a length in mm, cm or in, but always stores millimetres.

    The 0.13 plugin converted the displayed value and clamped it to the new
    range in the wrong order, which wrecked page sizes when you switched
    units. Here the stored value is millimetres and the display is only a
    view of it, so switching units can't change anything.
    """

    mmChanged = Signal(float)

    def __init__(self, mm: float = 0.0, lo_mm: float = 0.0, hi_mm: float = 1000.0, unit: str = "mm", parent=None):
        super().__init__(parent)
        self._mm, self._lo, self._hi, self._unit = mm, lo_mm, hi_mm, unit
        self.valueChanged.connect(self._typed)
        self.set_unit(unit)

    def set_unit(self, unit: str) -> None:
        f = MM_PER_UNIT[unit]
        self._unit = unit
        self.blockSignals(True)
        self.setDecimals(UNIT_DECIMALS[unit] + (1 if self._hi <= 10 else 0))
        self.setSingleStep({"mm": 0.5, "cm": 0.05, "in": 0.01}[unit])
        self.setRange(self._lo / f, self._hi / f)
        self.setSuffix(f" {unit}")
        self.setValue(self._mm / f)
        self.blockSignals(False)

    def mm(self) -> float:
        return self._mm

    def set_mm(self, mm: float) -> None:
        self._mm = mm
        self.blockSignals(True)
        self.setValue(mm / MM_PER_UNIT[self._unit])
        self.blockSignals(False)

    def _typed(self, value: float) -> None:
        self._mm = value * MM_PER_UNIT[self._unit]
        self.mmChanged.emit(self._mm)

    # The box follows the system's number format, so on a Spanish Windows it
    # shows "3,5 mm". Qt then refuses a typed "3.5" without a word, and the
    # numpad's decimal key types a dot. Reading a dot as the decimal point
    # too is safe: these boxes never show thousands separators.
    def _with_locale_point(self, text: str) -> str:
        return text.replace(".", self.locale().decimalPoint())

    def validate(self, text: str, pos: int):
        return super().validate(self._with_locale_point(text), pos)

    def valueFromText(self, text: str) -> float:
        return super().valueFromText(self._with_locale_point(text))


_TEXT_WITH_SPANS = re.compile(r'(<text [^>]*?)>((?:<tspan[^>]*>.*?</tspan>)+)</text>', re.S)
_SPAN = re.compile(r'<tspan x="([^"]+)" y="([^"]+)">(.*?)</tspan>', re.S)


def qt_friendly(svg: str) -> str:
    """
    The same SVG, with each balloon line as its own <text>.

    Qt's renderer follows SVG Tiny 1.2, which has no x/y on tspans, so it
    runs a balloon's lines together on one line. Only what Qt draws is
    changed: the file on disk keeps one text per balloon for Illustrator.
    """
    def split(m):
        return "".join(f'{m.group(1)} x="{x}" y="{y}">{t}</text>' for x, y, t in _SPAN.findall(m.group(2)))
    return _TEXT_WITH_SPANS.sub(split, svg)


def page_svg(page: Page, guides: bool = True, qt: bool = True, paper: bool = True) -> str:
    svg = page_to_svg(page)
    if not guides:
        svg = svg.replace('id="cpb-guides"', 'id="cpb-guides" display="none"', 1)
    if not paper:
        svg = svg.replace('id="cpb-paper"', 'id="cpb-paper" display="none"', 1)
    return qt_friendly(svg) if qt else svg


# Art images are big (a 600 dpi page is ~4000 × 6000 px), so they're loaded
# once, shrunk to screen size, and kept until the file changes.
_ART_CACHE: dict[str, tuple[float, QImage]] = {}
ART_PREVIEW_PX = 2200


def art_image(path: str) -> QImage | None:
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    hit = _ART_CACHE.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > ART_PREVIEW_PX:
        reader.setScaledSize(size.scaled(ART_PREVIEW_PX, ART_PREVIEW_PX, Qt.KeepAspectRatio))
    img = reader.read()
    if img.isNull():
        return None
    _ART_CACHE[path] = (stamp, img)
    return img


def render_page(p: QPainter, page: Page, target: QRectF, folder: str | None = None, guides: bool = True,
                renderer: QSvgRenderer | None = None) -> None:
    """
    Draw a page into ``target`` (screen pixels): paper, then a drawn page's
    art, then panels, letters and guides from page.svg.

    Qt can't follow page.svg's relative link to the art when the SVG comes
    from memory, so the art is painted here and the SVG's own paper is
    hidden (it would cover the art).
    """
    p.fillRect(target, QColor("#ffffff"))
    if page.art is not None and folder:
        img = art_image(os.path.join(folder, *page.art.href.split("/")))
        k = target.width() / page.size.canvas_w
        a = page.art.rect
        dest = QRectF(target.x() + a.x * k, target.y() + a.y * k, a.w * k, a.h * k)
        if img is not None:
            p.drawImage(dest, img)
        else:
            p.fillRect(dest, QColor(theme.DANGER_SOFT))
            p.setPen(QColor(theme.DANGER))
            p.drawText(dest, Qt.AlignCenter | Qt.TextWordWrap, f"Art missing:\n{page.art.href}")
    if renderer is None:
        renderer = QSvgRenderer(QByteArray(page_svg(page, guides=guides, paper=False).encode("utf-8")))
    renderer.render(p, target)


def page_thumbnail(page: Page, width: int = 64, folder: str | None = None) -> QPixmap:
    """A small picture of the page (no guides), for lists. ``folder`` is where a drawn page's art lives."""
    # A 0.6 mm line is under a pixel at thumbnail size, so thumbnails draw it thicker.
    thick = max(page.style.stroke_width, page.size.canvas_w * 1.4 / width)
    page = replace(page, style=replace(page.style, stroke_width=thick))
    h = round(width * page.size.canvas_h / page.size.canvas_w)
    if page.art is None:
        return icons.svg_pixmap(page_svg(page, guides=False), width, h)
    ratio = 2.0  # drawn at 2x, so thumbnails stay sharp on high-DPI screens
    pm = QPixmap(round(width * ratio), round(h * ratio))
    pm.fill(QColor("#ffffff"))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    render_page(painter, page, QRectF(0, 0, pm.width(), pm.height()), folder, guides=False)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


class PagePreview(QWidget):
    """The page on a neutral grey canvas, with the bleed tinted so you can see where it gets trimmed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Canvas")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(260, 320)
        self._page: Page | None = None
        self._renderer: QSvgRenderer | None = None

    def set_page(self, page: Page | None) -> None:
        self._page = page
        self._renderer = QSvgRenderer(QByteArray(page_svg(page).encode("utf-8"))) if page else None
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.CANVAS))
        if not self._page or not self._renderer:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "No page open")
            return
        s = self._page.size
        avail_w, avail_h = self.width() - 36, self.height() - 36
        scale = min(avail_w / s.canvas_w, avail_h / s.canvas_h)
        w, h = s.canvas_w * scale, s.canvas_h * scale
        x, y = (self.width() - w) / 2, (self.height() - h) / 2
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(QRectF(x + 3, y + 5, w, h), QColor(0, 0, 0, 50))  # soft drop shadow
        self._renderer.render(p, QRectF(x, y, w, h))
        # Tint the bleed: it's printed, then cut off.
        tint = QColor(243, 195, 211, 90)
        b = s.bleed * scale
        for r in (QRectF(x, y, w, b), QRectF(x, y + h - b, w, b), QRectF(x, y + b, b, h - 2 * b), QRectF(x + w - b, y + b, b, h - 2 * b)):
            p.fillRect(r, tint)


class GroupHeader(QWidget):
    """A Windows-7-style group title with a fading rule: "Pencils (3) ─────"."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 4)
        self.title = QLabel(text)
        self.title.setObjectName("GroupTitle")
        rule = QFrame()
        rule.setObjectName("GroupRule")
        lay.addWidget(self.title)
        lay.addWidget(rule, 1)


class Toast(QFrame):
    """A Windows 7 notification balloon in the bottom-right corner. Click to dismiss."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 12, 8)
        face = QLabel()
        face.setPixmap(icons.mascot(30))
        lay.addWidget(face, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("ToastTitle")
        self.text = QLabel()
        self.text.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.text)
        lay.addLayout(col, 1)
        self.setFixedWidth(320)
        self._timer = QTimer(self, singleShot=True, interval=4200, timeout=self.hide)
        self.hide()

    def show_message(self, title: str, text: str) -> None:
        self.title.setText(title)
        self.text.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move(parent.width() - self.width() - 18, parent.height() - self.height() - 44)
        self.raise_()
        self.show()
        self._timer.start()

    def mousePressEvent(self, _event) -> None:
        self.hide()
