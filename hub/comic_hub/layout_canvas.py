"""
The Page builder's canvas for hand-cut layouts (prototype).

    Select  drag a gutter to slide its cut (it keeps its angle); click an
            inset to select it, drag it to move, drag a handle to resize.
            Delete removes the selected inset, or merges the selected gutter.
    Knife   drag across a panel to cut it (insets too). Snaps to straight
            and 45°; Shift snaps to 15° steps, Ctrl moves the cut to the
            middle of the panel (like Maya's edge-loop centre), Alt is free.
            Dragging a gutter slides it, so you can cut and then slide.
    Inset   drag a rectangle: a panel on top of the others.
    Merge   click a gutter to join the panels on both sides, or an inset to remove it.

All the geometry is cpb_core.layouts.knife; this file turns mouse positions
into its 0..1 live-area coordinates and draws the feedback. A drag sends
``layout_preview`` while it moves and ``layout_edited`` once at the end, so
one drag is one undo step.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from cpb_core.layouts import knife

from . import theme
from .widgets import PagePreview

TOOLS = ("select", "knife", "inset", "merge")
SNAP_DEG = 6.0      # how close to straight / 45° a cut has to be to snap
PICK_MM = 3.0       # how close to a gutter counts as on it
HANDLE_PX = 5.0
MIN_INSET_MM = 8.0
# Handles on a selected inset: (x side, y side), -1 = left/top, 0 = middle, 1 = right/bottom.
HANDLES = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]
HANDLE_CURSORS = {(-1, -1): Qt.SizeFDiagCursor, (1, 1): Qt.SizeFDiagCursor, (1, -1): Qt.SizeBDiagCursor,
                  (-1, 1): Qt.SizeBDiagCursor, (0, -1): Qt.SizeVerCursor, (0, 1): Qt.SizeVerCursor,
                  (-1, 0): Qt.SizeHorCursor, (1, 0): Qt.SizeHorCursor}


def _seg_dist(q, a, b) -> float:
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / ((dx * dx + dy * dy) or 1)))
    return math.dist(q, (ax + t * dx, ay + t * dy))


class LayoutCanvas(PagePreview):
    layout_preview = Signal(dict)  # while dragging
    layout_edited = Signal(dict)   # a finished edit: one undo step
    message = Signal(str)          # feedback for the hint line (a refused cut, say)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.tool = "select"
        self.selection = None      # ("inset", i) or ("cut", where)
        self._hover = None
        self._drag = None          # what the current drag does, see mousePressEvent
        self._mods = Qt.NoModifier

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

    def set_page(self, page) -> None:
        super().set_page(page)
        # A selection that no longer exists (after undo, say) is dropped.
        if page is not None and self.selection is not None:
            kind, what = self.selection
            lay = self.layout()
            if kind == "inset" and what >= len(knife.insets(lay)):
                self.selection = None
            if kind == "cut" and what not in [w for w, *_ in knife.cut_segments(lay)]:
                self.selection = None

    # ---------- hit testing ----------
    def _inset_rect_px(self, i: int) -> QRectF:
        x, y, w, h = knife.insets(self.layout())[i]["rect"]
        return QRectF(self.unnorm((x, y)), self.unnorm((x + w, y + h)))

    def _handle_at(self, pos: QPointF):
        if not self.selection or self.selection[0] != "inset":
            return None
        r = self._inset_rect_px(self.selection[1])
        for hx, hy in HANDLES:
            c = QPointF(r.center().x() + hx * r.width() / 2, r.center().y() + hy * r.height() / 2)
            if abs(c.x() - pos.x()) <= HANDLE_PX + 2 and abs(c.y() - pos.y()) <= HANDLE_PX + 2:
                return (hx, hy)
        return None

    def _gutter_at(self, mm: QPointF):
        live = self._live()
        q = (mm.x(), mm.y())
        best = None
        for where, a, b in knife.cut_segments(self.layout()):
            pa = (live.x + a[0] * live.w, live.y + a[1] * live.h)
            pb = (live.x + b[0] * live.w, live.y + b[1] * live.h)
            dist = _seg_dist(q, pa, pb)
            if dist <= max(PICK_MM, self._page.gutter / 2 + 0.5) and (best is None or dist < best[0]):
                best = (dist, where)
        return best[1] if best else None

    def _hit(self, pos: QPointF):
        """What's under the pointer for Select / Knife / Merge: a handle, a gutter or an inset."""
        h = self._handle_at(pos)
        if h is not None:
            return ("handle", h)
        mm = self.to_mm(pos)
        g = self._gutter_at(mm)
        if g is not None:
            return ("cut", g)
        i = knife.inset_at(self.layout(), self.norm(mm))
        return ("inset", i) if i >= 0 else None

    # ---------- knife snapping ----------
    def _cut_line(self, a: QPointF, b: QPointF, mods):
        """The cut as two page points (0..1), with angle snapping and Shift's centring applied."""
        if not mods & Qt.AltModifier:
            dx, dy = b.x() - a.x(), b.y() - a.y()
            length = math.hypot(dx, dy)
            ang = math.degrees(math.atan2(dy, dx))
            target = round(ang / 15) * 15 if mods & Qt.ShiftModifier else round(ang / 45) * 45
            if mods & Qt.ShiftModifier or abs(ang - target) <= SNAP_DEG:
                r = math.radians(target)
                b = QPointF(a.x() + length * math.cos(r), a.y() + length * math.sin(r))
        p1, p2 = self.norm(a), self.norm(b)
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        leaf = knife.leaf_at(self.layout(), mid)
        if leaf is not None and mods & Qt.ControlModifier and math.dist(p1, p2) > 1e-6:
            p1, p2 = knife.centred(leaf.points, p1, p2)
        return p1, p2, leaf

    # ---------- mouse ----------
    def mousePressEvent(self, e) -> None:
        if not self._page or e.button() != Qt.LeftButton:
            return
        self.setFocus()
        pos, mm = e.position(), self.to_mm(e.position())
        lay = self.layout()
        hit = self._hit(pos) if self.tool in ("select", "knife", "merge") else None
        if self.tool == "merge":
            if hit is None or hit[0] == "handle":
                self.message.emit("Click on a gutter to join the panels on both sides, or on an inset to remove it.")
                return
            self.selection = self._hover = None
            self.layout_edited.emit(knife.remove_inset(lay, hit[1]) if hit[0] == "inset" else knife.merge(lay, hit[1]))
            return
        if hit and hit[0] == "cut":                       # Select or Knife on a gutter: slide it
            self.selection = hit
            self._drag = ("slide", hit[1], mm, lay)
        elif self.tool == "select" and hit and hit[0] == "handle":
            i = self.selection[1]
            self._drag = ("resize", i, hit[1], mm, list(knife.insets(lay)[i]["rect"]), lay)
        elif self.tool == "select" and hit and hit[0] == "inset":
            self.selection = hit
            self._drag = ("move", hit[1], mm, list(knife.insets(lay)[hit[1]]["rect"]), lay)
        elif self.tool == "select":
            self.selection = None
            self._drag = None
        else:                                             # Knife or Inset: draw
            self._drag = ("draw", mm, mm)
        self._mods = e.modifiers()
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if not self._page:
            return
        pos, mm = e.position(), self.to_mm(e.position())
        self._mods = e.modifiers()
        d = self._drag
        if d is None:
            self._hover = self._hit(pos) if self.tool != "inset" else None
            kind = self._hover[0] if self._hover else None
            if kind == "handle":
                self.setCursor(HANDLE_CURSORS[self._hover[1]])
            elif kind == "cut":
                self.setCursor(Qt.SplitVCursor if self.tool != "merge" else Qt.PointingHandCursor)
            elif kind == "inset" and self.tool in ("select", "merge"):
                self.setCursor(Qt.SizeAllCursor if self.tool == "select" else Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.CrossCursor if self.tool in ("knife", "inset") else Qt.ArrowCursor)
            self.update()
            return
        if d[0] == "draw":
            self._drag = ("draw", d[1], mm)
            self.update()
            return
        new = self._dragged(mm)
        if new is not None:
            self._pending = new
            self.layout_preview.emit(new)

    def _dragged(self, mm: QPointF):
        """The layout a slide / move / resize drag has made so far, or None if refused."""
        d = self._drag
        live = self._live()
        try:
            if d[0] == "slide":
                _, where, start, base = d
                return knife.slide(base, where, (mm.x() - start.x()) / live.w, (mm.y() - start.y()) / live.h)
            if d[0] == "move":
                _, i, start, (x, y, w, h), base = d
                dx, dy = (mm.x() - start.x()) / live.w, (mm.y() - start.y()) / live.h
                return knife.set_inset_rect(base, i, x + dx, y + dy, w, h)
            if d[0] == "resize":
                _, i, (hx, hy), start, (x, y, w, h), base = d
                dx, dy = (mm.x() - start.x()) / live.w, (mm.y() - start.y()) / live.h
                x0, y0, x1, y1 = x, y, x + w, y + h
                if hx < 0: x0 = min(x0 + dx, x1 - MIN_INSET_MM / live.w)
                if hx > 0: x1 = max(x1 + dx, x0 + MIN_INSET_MM / live.w)
                if hy < 0: y0 = min(y0 + dy, y1 - MIN_INSET_MM / live.h)
                if hy > 0: y1 = max(y1 + dy, y0 + MIN_INSET_MM / live.h)
                return knife.set_inset_rect(base, i, x0, y0, x1 - x0, y1 - y0)
        except ValueError as err:
            self.message.emit(f"Can't go further: {err}.")
        return None

    def mouseReleaseEvent(self, e) -> None:
        d, self._drag = self._drag, None
        if d is None:
            return
        mm = self.to_mm(e.position())
        if d[0] != "draw":
            new = getattr(self, "_pending", None)
            self._pending = None
            if new is not None:
                self.layout_edited.emit(new)
            self.update()
            return
        a, b = d[1], mm
        self.update()
        if self.tool == "knife":
            if math.dist((a.x(), a.y()), (b.x(), b.y())) < 3:
                return  # a click, not a cut
            p1, p2, _leaf = self._cut_line(a, b, e.modifiers())
            try:
                self.layout_edited.emit(knife.cut(self.layout(), p1, p2))
            except ValueError as err:
                self.message.emit(f"No cut: {err}.")
        elif self.tool == "inset":
            x0, x1 = sorted((a.x(), b.x())); y0, y1 = sorted((a.y(), b.y()))
            if x1 - x0 < MIN_INSET_MM or y1 - y0 < MIN_INSET_MM:
                self.message.emit(f"Insets need to be at least {MIN_INSET_MM:g} mm each way.")
                return
            (nx0, ny0), (nx1, ny1) = self.norm(QPointF(x0, y0)), self.norm(QPointF(x1, y1))
            new = knife.add_inset(self.layout(), nx0, ny0, nx1 - nx0, ny1 - ny0)
            self.selection = ("inset", len(knife.insets(new)) - 1)
            self.layout_edited.emit(new)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selection and self._page:
            kind, what = self.selection
            self.selection = None
            lay = self.layout()
            self.layout_edited.emit(knife.remove_inset(lay, what) if kind == "inset" else knife.merge(lay, what))
            return
        if e.key() == Qt.Key_Escape:
            self.selection = None
            self._drag = None
            self.update()
            return
        super().keyPressEvent(e)

    # ---------- painting ----------
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._page:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lay = self.layout()
        accent, tint = QColor(theme.ACCENT), QColor(217, 86, 138, 34)
        if self.tool in ("select", "merge", "knife"):
            for where, a, b in knife.cut_segments(lay):
                on = ("cut", where) in (self._hover, self.selection)
                if on or self.tool != "knife":
                    p.setPen(QPen(accent, 4 if on else 1.2, Qt.SolidLine if on else Qt.DotLine))
                    p.drawLine(self.unnorm(a), self.unnorm(b))
        for state in (self._hover, self.selection):
            if state and state[0] == "inset" and state[1] < len(knife.insets(lay)) and self.tool != "knife":
                p.setPen(QPen(accent, 2)); p.setBrush(tint)
                p.drawRect(self._inset_rect_px(state[1]))
        if self.selection and self.selection[0] == "inset" and self.tool == "select":
            r = self._inset_rect_px(self.selection[1])
            p.setPen(QPen(QColor(theme.ACCENT_TEXT), 1)); p.setBrush(QColor("#ffffff"))
            for hx, hy in HANDLES:
                c = QPointF(r.center().x() + hx * r.width() / 2, r.center().y() + hy * r.height() / 2)
                p.drawRect(QRectF(c.x() - HANDLE_PX, c.y() - HANDLE_PX, 2 * HANDLE_PX, 2 * HANDLE_PX))
        d = self._drag
        if not d or d[0] != "draw":
            return
        a, b = d[1], d[2]
        if self.tool == "knife":
            if math.dist((a.x(), a.y()), (b.x(), b.y())) <= 0.5:
                return
            p1, p2, leaf = self._cut_line(a, b, self._mods)
            if leaf is None:
                return
            p.setPen(Qt.NoPen); p.setBrush(tint)
            p.drawPolygon(QPolygonF([self.unnorm(pt) for pt in leaf.points]))
            span = knife.crossing(leaf.points, p1, p2)
            if span:
                p.setPen(QPen(accent, 2, Qt.DashLine))
                p.drawLine(self.unnorm(span[0]), self.unnorm(span[1]))
                live = self._live()
                ang = math.degrees(math.atan2((p2[1] - p1[1]) * live.h, (p2[0] - p1[0]) * live.w)) % 180
                label = f"{ang:.0f}°" + (" · centre" if self._mods & Qt.ControlModifier else "")
                p.setPen(QColor(theme.ACCENT_TEXT))
                p.drawText(self.to_px(b.x(), b.y()) + QPointF(12, -10), label)
        elif self.tool == "inset":
            p.setPen(QPen(accent, 2, Qt.DashLine)); p.setBrush(tint)
            p.drawRect(QRectF(self.to_px(a.x(), a.y()), self.to_px(b.x(), b.y())).normalized())
