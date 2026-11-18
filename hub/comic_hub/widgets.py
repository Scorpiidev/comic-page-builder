"""Small reusable widgets: unit-safe spin boxes, page previews, the toast."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
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


def page_svg(page: Page, guides: bool = True) -> str:
    svg = page_to_svg(page)
    if not guides:
        svg = svg.replace('id="cpb-guides"', 'id="cpb-guides" display="none"', 1)
    return svg


def page_thumbnail(page: Page, width: int = 64) -> QPixmap:
    """A small picture of the page's panels (no guides), for lists."""
    # A 0.6 mm line is under a pixel at thumbnail size, so thumbnails draw it thicker.
    thick = max(page.style.stroke_width, page.size.canvas_w * 1.4 / width)
    page = replace(page, style=replace(page.style, stroke_width=thick))
    h = round(width * page.size.canvas_h / page.size.canvas_w)
    return icons.svg_pixmap(page_svg(page, guides=False), width, h)


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
