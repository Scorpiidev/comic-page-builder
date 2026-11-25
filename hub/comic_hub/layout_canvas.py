"""
The Page builder's canvas for manual layouts (prototype): cut panels with a
knife at any angle, merge cuts back, and draw inset panels on top.

    Knife   drag a line across a panel. It snaps to straight and 45°;
            Shift snaps to 15° steps, Alt turns snapping off.
    Inset   drag a rectangle: a panel on top of the others.
    Merge   click a gutter to remove that cut (and the cuts inside it),
            or click an inset to remove it.

All the geometry is cpb_core.layouts.knife; this file only turns mouse
positions into its 0..1 live-area coordinates and draws the feedback.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from cpb_core.layouts import knife

from . import theme
from .widgets import PagePreview

TOOLS = ("knife", "inset", "merge")
SNAP_DEG = 6.0      # how close to straight / 45° a cut has to be to snap
PICK_MM = 4.0       # how close to a gutter a Merge click has to be
MIN_INSET_MM = 8.0


def _seg_dist(q, a, b) -> float:
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / ((dx * dx + dy * dy) or 1)))
    return math.dist(q, (ax + t * dx, ay + t * dy))


class LayoutCanvas(PagePreview):
    layout_edited = Signal(dict)   # a new manual layout
    message = Signal(str)          # feedback for the hint line (a refused cut, say)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.tool = "knife"
        self._press: QPointF | None = None   # page mm
        self._now: QPointF | None = None
        self._hover = None                   # ("cut", path) or ("inset", i)

    # ---------- coordinates ----------
    def _frame(self):
        s = self._page.size
        scale = min((self.width() - 36) / s.canvas_w, (self.height() - 36) / s.canvas_h)
        return (self.width() - s.canvas_w * scale) / 2, (self.height() - s.canvas_h * scale) / 2, scale

    def to_mm(self, pos: QPointF) -> QPointF:
        x0, y0, k = self._frame()
        return QPointF((pos.x() - x0) / k, (pos.y() - y0) / k)

    def to_px(self, x: float, y: float) -> QPointF:
        x0, y0, k = self._frame()
        return QPointF(x0 + x * k, y0 + y * k)

    def _live(self):
        return self._page.geometry().live

    def norm(self, mm: QPointF) -> tuple[float, float]:
        live = self._live()
        return (mm.x() - live.x) / live.w, (mm.y() - live.y) / live.h

    def unnorm(self, pt) -> QPointF:
        live = self._live()
        return self.to_px(live.x + pt[0] * live.w, live.y + pt[1] * live.h)

    def layout(self) -> dict:
        lay = self._page.layout
        if lay.get("kind") == "manual":
            return lay
        # Presets and random layouts become a cut tree the first time you edit them.
        return knife.from_cells(self._page.cells) or knife.empty()

    # ---------- snapping ----------
    def _snapped_end(self, modifiers) -> QPointF:
        a, b = self._press, self._now
        if modifiers & Qt.AltModifier:
            return b
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx))
        if modifiers & Qt.ShiftModifier:
            target = round(ang / 15) * 15
        else:
            target = round(ang / 45) * 45
            if abs(ang - target) > SNAP_DEG:
                return b
        r = math.radians(target)
        return QPointF(a.x() + length * math.cos(r), a.y() + length * math.sin(r))

    # ---------- mouse ----------
    def mousePressEvent(self, e) -> None:
        if not self._page or e.button() != Qt.LeftButton:
            return
        self.setFocus()
        if self.tool == "merge":
            self._merge_at(self.to_mm(e.position()))
            return
        self._press = self._now = self.to_mm(e.position())
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if not self._page:
            return
        mm = self.to_mm(e.position())
        if self._press is not None:
            self._now = mm
            self._mods = e.modifiers()
        elif self.tool == "merge":
            self._hover = self._pick(mm)
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._press is None:
            return
        a, self._now = self._press, self.to_mm(e.position())
        b = self._snapped_end(e.modifiers()) if self.tool == "knife" else self._now
        self._press = self._now = None
        self.update()
        if self.tool == "knife":
            if math.dist((a.x(), a.y()), (b.x(), b.y())) < 3:
                return  # a click, not a cut
            try:
                self.layout_edited.emit(knife.cut(self.layout(), self.norm(a), self.norm(b)))
            except ValueError as err:
                self.message.emit(f"No cut: {err}.")
        elif self.tool == "inset":
            x0, x1 = sorted((a.x(), b.x())); y0, y1 = sorted((a.y(), b.y()))
            if x1 - x0 < MIN_INSET_MM or y1 - y0 < MIN_INSET_MM:
                self.message.emit(f"Insets need to be at least {MIN_INSET_MM:g} mm each way.")
                return
            (nx0, ny0), (nx1, ny1) = self.norm(QPointF(x0, y0)), self.norm(QPointF(x1, y1))
            self.layout_edited.emit(knife.add_inset(self.layout(), nx0, ny0, nx1 - nx0, ny1 - ny0))

    def _pick(self, mm: QPointF):
        """The inset under the pointer, else the nearest cut within reach."""
        lay = self.layout()
        live = self._live()
        q = (mm.x(), mm.y())
        for i, (x, y, w, h) in reversed(list(enumerate(lay.get("insets", [])))):
            if live.x + x * live.w <= q[0] <= live.x + (x + w) * live.w and live.y + y * live.h <= q[1] <= live.y + (y + h) * live.h:
                return ("inset", i)
        best = None
        for path, a, b in knife.cut_segments(lay):
            pa = (live.x + a[0] * live.w, live.y + a[1] * live.h)
            pb = (live.x + b[0] * live.w, live.y + b[1] * live.h)
            dist = _seg_dist(q, pa, pb)
            if dist <= PICK_MM and (best is None or dist < best[0]):
                best = (dist, path)
        return ("cut", best[1]) if best else None

    def _merge_at(self, mm: QPointF) -> None:
        hit = self._pick(mm)
        if hit is None:
            self.message.emit("Click on a gutter to merge the panels on both sides, or on an inset to remove it.")
            return
        kind, what = hit
        lay = self.layout()
        self._hover = None
        self.layout_edited.emit(knife.remove_inset(lay, what) if kind == "inset" else knife.merge(lay, what))

    # ---------- painting ----------
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._page:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lay = self.layout()
        if self.tool == "merge":
            for path, a, b in knife.cut_segments(lay):
                on = self._hover == ("cut", path)
                p.setPen(QPen(QColor(theme.ACCENT), 4 if on else 1.5, Qt.SolidLine if on else Qt.DashLine))
                p.drawLine(self.unnorm(a), self.unnorm(b))
            if self._hover and self._hover[0] == "inset":
                x, y, w, h = lay["insets"][self._hover[1]]
                p.setPen(QPen(QColor(theme.ACCENT), 3)); p.setBrush(QColor(217, 86, 138, 40))
                p.drawRect(QRectF(self.unnorm((x, y)), self.unnorm((x + w, y + h))))
        if self._press is None or self._now is None:
            return
        if self.tool == "knife":
            b = self._snapped_end(getattr(self, "_mods", Qt.NoModifier))
            a = self._press
            mid = self.norm(QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
            leaf = knife.leaf_at(lay, mid)
            span = knife.crossing(leaf.points, self.norm(a), self.norm(b)) if leaf and math.dist((a.x(), a.y()), (b.x(), b.y())) > 0.5 else None
            if leaf is not None:
                p.setPen(Qt.NoPen); p.setBrush(QColor(217, 86, 138, 30))
                p.drawPolygon(QPolygonF([self.unnorm(pt) for pt in leaf.points]))
            if span:
                p.setPen(QPen(QColor(theme.ACCENT), 2, Qt.DashLine))
                p.drawLine(self.unnorm(span[0]), self.unnorm(span[1]))
                ang = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x())) % 180
                p.setPen(QColor(theme.ACCENT_TEXT))
                p.drawText(self.to_px(b.x(), b.y()) + QPointF(10, -8), f"{ang:.0f}°")
        elif self.tool == "inset":
            p.setPen(QPen(QColor(theme.ACCENT), 2, Qt.DashLine)); p.setBrush(QColor(217, 86, 138, 30))
            p.drawRect(QRectF(self.to_px(self._press.x(), self._press.y()), self.to_px(self._now.x(), self._now.y())).normalized())
