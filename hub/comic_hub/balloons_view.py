"""
The Balloons screen: place and edit balloons on a page (docs/DESIGN.md section 10).

The canvas draws balloons itself from their parameters instead of rendering
page.svg's Letters layer, because it needs handles on top, and because Qt's
SVG renderer can't place a balloon's lines (it ignores tspan x/y).

Body and tail are edited separately (D6):
- drag inside a balloon to move the body; the tail's tip stays put unless
  "Tip follows body" is on;
- the pink corner handles resize the body (auto-size turns off, the text
  re-wraps; "Fit to text" turns it back on);
- the blue handles are the tail: one on the rim where it leaves the body,
  one at the tip.
Keyboard: Tab switches body / tail, arrows nudge (Shift: 5 mm), Delete removes.
Zoom: Ctrl+wheel (around the cursor), Ctrl+= / Ctrl+-, Ctrl+0 fits the page.
Pan: the wheel (Shift: sideways), middle-drag, or Space+drag.
Undo: Ctrl+Z / Ctrl+Y. One drag, one stretch of typing or one run of nudges
is one step.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import replace

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from cpb_core.balloons import KINDS, Balloon, BalloonFont, Tail, fit_balloon, outline_path, tail_base_point
from cpb_core.balloons.text import layout_lines
from cpb_core.lettering import ROLES, cap_height_mm, recommend_pt, verdict
from cpb_core.model import Page
from cpb_core.project import Project
from cpb_core.svg.letters import next_number

from . import theme
from .widgets import page_svg, render_page

KIND_LABELS = {"speech": "Speech", "thought": "Thought", "shout": "Shout", "whisper": "Whisper", "caption": "Caption"}
ROLE_LABELS = {"dialogue": "Dialogue", "caption": "Caption", "whisper": "Whisper", "sfx": "SFX"}
DEFAULT_ROLE = {"speech": "dialogue", "thought": "dialogue", "shout": "dialogue", "whisper": "whisper", "caption": "caption"}
HANDLE = 4.0          # handle half-size in screen pixels
NUDGE, BIG_NUDGE = 0.5, 5.0   # mm
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.5, 12.0, 1.25   # zoom 1 = the whole page fits
FILLS = (("White", "#ffffff"), ("None", None), ("Pale yellow", "#fff8d6"))

_REF_PX = 100.0  # fonts are measured and drawn at 100 px, then scaled: Qt rounds tiny pixel sizes


def qfont(font: BalloonFont) -> QFont:
    f = QFont(font.family)
    f.setStyleName(font.style)
    f.setPixelSize(int(_REF_PX))
    return f


_metrics: dict[tuple[str, str], QFontMetricsF] = {}


def qt_measure(font: BalloonFont):
    """measure(text) -> width in mm, from Qt's real glyph widths, for cpb_core's text fitting."""
    key = (font.family, font.style)
    if key not in _metrics:
        _metrics[key] = QFontMetricsF(qfont(font))
    fm = _metrics[key]
    mm_per_ref = font.size_pt * 25.4 / 72 / _REF_PX
    return lambda s: fm.horizontalAdvance(s) * mm_per_ref


_TOKEN = re.compile(r"[MLCZ]|-?\d*\.?\d+(?:e-?\d+)?")


def qpath(d: str) -> QPainterPath:
    """A QPainterPath from the M/L/C/Z path data cpb_core writes."""
    path, tokens, i = QPainterPath(), _TOKEN.findall(d), 0
    nums = lambda n: [float(t) for t in tokens[i + 1:i + 1 + n]]
    while i < len(tokens):
        cmd = tokens[i]
        if cmd == "M":
            x, y = nums(2); path.moveTo(x, y); i += 3
        elif cmd == "L":
            x, y = nums(2); path.lineTo(x, y); i += 3
        elif cmd == "C":
            a = nums(6); path.cubicTo(*a); i += 7
        elif cmd == "Z":
            path.closeSubpath(); i += 1
        else:
            i += 1
    return path


def default_font_for(project: Project | None, role: str, ui_family: str) -> BalloonFont:
    """The role's Lettering preset, or a readable stand-in (the UI font) until there is one."""
    font = project.balloon_font(role) if project else None
    if font is not None:
        return font
    return BalloonFont(family=ui_family, size_pt=recommend_pt(0.7, role if role in ("dialogue", "caption", "whisper") else "dialogue"))


def fitted(b: Balloon) -> Balloon:
    return fit_balloon(b, qt_measure(b.font))


def rim_point(b: Balloon) -> QPointF | None:
    """Where the tail leaves the body (the blue rim handle): the core's answer, so it matches the drawing."""
    pt = tail_base_point(b) if b.has_tail else None
    return None if pt is None else QPointF(*pt)


class BalloonCanvas(QWidget):
    """The page with its balloons, and handles on the selected one. Works in page mm."""

    edited = Signal(object)        # a Balloon that changed
    selected_changed = Signal(object)   # a balloon number, or None
    delete_requested = Signal()
    gesture_started = Signal()     # a press on a balloon: what follows is one undo step
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Canvas")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 360)
        self.setMouseTracking(True)
        self.page: Page | None = None
        self.folder: str | None = None
        self.balloons: list[Balloon] = []
        self.selected: int | None = None
        self.part = "body"   # what the keyboard moves: "body" or "tail"
        self._renderer: QSvgRenderer | None = None
        self._drag: tuple | None = None
        self.zoom = 1.0
        self.pan = QPointF(0, 0)        # screen px, added to the centred position
        self._panning: QPointF | None = None
        self._space = False

    # ---------- data ----------
    def set_page(self, page: Page | None, folder: str | None = None) -> None:
        if page is None or self.page is None or page.number != getattr(self.page, "number", None):
            self.fit()  # a new page starts whole
        self.page, self.folder = page, folder
        # Panels and guides come from page.svg; balloons are drawn here instead (with handles).
        self._renderer = QSvgRenderer(QByteArray(page_svg(replace(page, balloons=()), paper=False).encode())) if page else None
        self.update()

    def set_balloons(self, balloons: list[Balloon], selected: int | None) -> None:
        self.balloons, self.selected = balloons, selected
        self.update()

    def current(self) -> Balloon | None:
        return next((b for b in self.balloons if b.number == self.selected), None)

    # ---------- page mm <-> screen ----------
    def _frame(self) -> tuple[float, float, float]:
        s = self.page.size
        scale = min((self.width() - 36) / s.canvas_w, (self.height() - 36) / s.canvas_h) * self.zoom
        return ((self.width() - s.canvas_w * scale) / 2 + self.pan.x(),
                (self.height() - s.canvas_h * scale) / 2 + self.pan.y(), scale)

    # ---------- zoom and pan ----------
    def fit(self) -> None:
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def zoom_to(self, zoom: float, around: QPointF | None = None) -> None:
        """Zoom keeping the page point under `around` (screen px; default: the middle) where it is."""
        if not self.page:
            return
        around = around if around is not None else QPointF(self.width() / 2, self.height() / 2)
        held = self.to_mm(around)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        self.pan += around - self.to_px(held)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, e) -> None:
        if not self.page:
            return
        dy = e.angleDelta().y()
        if e.modifiers() & Qt.ControlModifier:
            self.zoom_to(self.zoom * ZOOM_STEP ** (dy / 120), e.position())
        elif e.modifiers() & Qt.ShiftModifier:
            self.pan += QPointF(dy / 2, 0); self.update()
        else:
            self.pan += QPointF(e.angleDelta().x() / 2, dy / 2); self.update()

    def keyReleaseEvent(self, e) -> None:
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = False
            self.setCursor(Qt.ArrowCursor)
        super().keyReleaseEvent(e)

    def to_mm(self, pos: QPointF) -> QPointF:
        x0, y0, k = self._frame()
        return QPointF((pos.x() - x0) / k, (pos.y() - y0) / k)

    def to_px(self, pt: QPointF) -> QPointF:
        x0, y0, k = self._frame()
        return QPointF(x0 + pt.x() * k, y0 + pt.y() * k)

    # ---------- painting ----------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.CANVAS))
        if not self.page or not self._renderer:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "No page open")
            return
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        x0, y0, k = self._frame()
        s = self.page.size
        p.fillRect(QRectF(x0 + 3, y0 + 5, s.canvas_w * k, s.canvas_h * k), QColor(0, 0, 0, 50))
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        render_page(p, self.page, QRectF(x0, y0, s.canvas_w * k, s.canvas_h * k), self.folder, renderer=self._renderer)
        p.save()
        p.translate(x0, y0)
        p.scale(k, k)
        for b in self.balloons:
            draw_balloon(p, b)
        p.restore()
        b = self.current()
        if b is not None:
            self._draw_handles(p, b)

    def _handles(self, b: Balloon) -> dict[str, QPointF]:
        h = {f"corner{i}": QPointF(b.cx + sx * b.rx, b.cy + sy * b.ry)
             for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1)))}
        rim = rim_point(b)
        if rim is not None:
            h["rim"] = rim
            h["tip"] = QPointF(b.tail.tip_x, b.tail.tip_y)
        return h

    def _draw_handles(self, p: QPainter, b: Balloon) -> None:
        tl, br = self.to_px(QPointF(b.cx - b.rx, b.cy - b.ry)), self.to_px(QPointF(b.cx + b.rx, b.cy + b.ry))
        body_pen = QPen(QColor(theme.ACCENT), 2 if self.part == "body" else 1, Qt.DashLine)
        p.setPen(body_pen); p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(tl, br))
        tail_color = QColor(theme.TAIL)
        for name, pt in self._handles(b).items():
            c = self.to_px(pt)
            if name.startswith("corner"):
                p.setPen(QPen(QColor(theme.ACCENT_TEXT), 1)); p.setBrush(QColor("#ffffff"))
                p.drawRect(QRectF(c.x() - HANDLE, c.y() - HANDLE, 2 * HANDLE, 2 * HANDLE))
            else:
                p.setPen(QPen(tail_color, 2 if self.part == "tail" else 1)); p.setBrush(QColor("#ffffff") if name == "rim" else tail_color)
                p.drawEllipse(c, HANDLE + 1, HANDLE + 1)
        if b.has_tail:
            p.setPen(QPen(tail_color, 1, Qt.DotLine))
            p.drawLine(self.to_px(self._handles(b)["rim"]), self.to_px(QPointF(b.tail.tip_x, b.tail.tip_y)))

    # ---------- mouse ----------
    def _hit(self, pos: QPointF) -> tuple[int | None, str | None]:
        b = self.current()
        if b is not None:
            for name, pt in self._handles(b).items():
                c = self.to_px(pt)
                if abs(c.x() - pos.x()) <= HANDLE + 3 and abs(c.y() - pos.y()) <= HANDLE + 3:
                    return b.number, name
        mm = self.to_mm(pos)
        for b in reversed(self.balloons):  # topmost first
            if qpath(outline_path(b)).contains(mm) or QRectF(b.cx - b.rx, b.cy - b.ry, 2 * b.rx, 2 * b.ry).contains(mm):
                return b.number, "body"
        return None, None

    def mousePressEvent(self, e) -> None:
        if not self.page:
            return
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self._space):
            self._panning = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return
        self.setFocus()
        number, part = self._hit(e.position())
        if number != self.selected:
            self.selected = number
            self.selected_changed.emit(number)
        if number is None:
            self._drag = None
        else:
            self.part = "tail" if part in ("rim", "tip") else "body"
            self._drag = (part, self.to_mm(e.position()), self.current())
            self.gesture_started.emit()
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._panning is not None:
            self.pan += e.position() - self._panning
            self._panning = e.position()
            self.update()
            return
        if not self._drag:
            if self._space:
                self.setCursor(Qt.OpenHandCursor)
                return
            number, part = self._hit(e.position()) if self.page else (None, None)
            self.setCursor({None: Qt.ArrowCursor, "body": Qt.SizeAllCursor, "rim": Qt.PointingHandCursor,
                            "tip": Qt.CrossCursor}.get(part, Qt.SizeFDiagCursor))
            return
        part, start, b0 = self._drag
        now = self.to_mm(e.position())
        dx, dy = now.x() - start.x(), now.y() - start.y()
        if part == "body":
            b = b0.moved(dx, dy)
        elif part == "tip":
            b = replace(b0, tail=replace(b0.tail, tip_x=round(now.x(), 3), tip_y=round(now.y(), 3)))
        elif part == "rim":
            angle = math.degrees(math.atan2(now.y() - b0.cy, now.x() - b0.cx))
            b = replace(b0, tail=replace(b0.tail, base_angle=round(angle, 1)))
        else:  # a corner: resize around the centre, so the text stays where it is
            b = fitted(replace(b0, rx=max(3.0, round(abs(now.x() - b0.cx), 3)),
                               ry=max(3.0, round(abs(now.y() - b0.cy), 3)), auto_size=False))
        self.edited.emit(b)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag = None
        if self._panning is not None:
            self._panning = None
            self.setCursor(Qt.OpenHandCursor if self._space else Qt.ArrowCursor)

    # ---------- keyboard ----------
    def focusNextPrevChild(self, _next: bool) -> bool:
        return False  # Tab belongs to the canvas: it switches body / tail

    nudged = Signal(str)   # "nudge-<number>-<part>": consecutive nudges make one undo step

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key == Qt.Key_Space:
            if not e.isAutoRepeat():
                self._space = True
                self.setCursor(Qt.OpenHandCursor)
            return
        if e.modifiers() & Qt.ControlModifier and self.page:
            if key == Qt.Key_0:
                self.fit(); return
            if key in (Qt.Key_Plus, Qt.Key_Equal):
                self.zoom_to(self.zoom * ZOOM_STEP); return
            if key == Qt.Key_Minus:
                self.zoom_to(self.zoom / ZOOM_STEP); return
        b = self.current()
        if b is None:
            return super().keyPressEvent(e)
        if key in (Qt.Key_Tab, Qt.Key_Backtab):
            self.part = "tail" if self.part == "body" and b.has_tail else "body"
            self.update()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
            return
        step = BIG_NUDGE if e.modifiers() & Qt.ShiftModifier else NUDGE
        moves = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}
        if key not in moves:
            return super().keyPressEvent(e)
        dx, dy = moves[key]
        self.nudged.emit(f"nudge-{b.number}-{self.part}")
        if self.part == "tail" and b.has_tail:
            self.edited.emit(replace(b, tail=replace(b.tail, tip_x=b.tail.tip_x + dx, tip_y=b.tail.tip_y + dy)))
        else:
            self.edited.emit(b.moved(dx, dy))


def draw_balloon(p: QPainter, b: Balloon) -> None:
    """Paint one balloon in page mm (the painter is already scaled to mm)."""
    pen = QPen(QColor(b.stroke), b.stroke_width)
    pen.setJoinStyle(Qt.RoundJoin)
    if b.kind == "whisper":
        pen.setDashPattern([1.2 / max(b.stroke_width, 0.01), 0.9 / max(b.stroke_width, 0.01)])  # same dashes as page.svg
    p.setPen(pen if b.stroke_width > 0 else Qt.NoPen)
    p.setBrush(QColor(b.fill) if b.fill else Qt.NoBrush)
    p.drawPath(qpath(outline_path(b)))
    if not b.lines:
        return
    measure = qt_measure(b.font)
    block = layout_lines(b.lines, b, measure)
    f = qfont(b.font)
    k = b.font.size_pt * 25.4 / 72 / _REF_PX
    # Text goes in as outlines, not drawText: Windows' ClearType gives scaled
    # text coloured fringes, and outlines stay crisp at any zoom.
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(b.font.color))
    for line, y in zip(block.lines, block.baselines(b.cy)):
        glyphs = QPainterPath()
        glyphs.addText(QPointF(-measure(line) / k / 2, 0), f, line)
        p.save()
        p.translate(b.cx, y)
        p.scale(k, k)
        p.drawPath(glyphs)
        p.restore()


class BalloonsView(QWidget):
    """Edit one page's balloons. Nothing is written until Save letters."""

    dirty_changed = Signal(bool)
    status_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.page: Page | None = None
        self.saved: tuple[Balloon, ...] = ()
        self.balloons: list[Balloon] = []
        self.edited_elsewhere: list[int] = []
        self._loading = False
        # Undo: snapshots of (balloons, selected number). Edits that share a
        # key in a row (one drag, one stretch of typing) make a single step.
        self.undo_stack: list[tuple] = []
        self.redo_stack: list[tuple] = []
        self._last_key: str | None = None
        self._gesture = 0
        self._nudge_key: str | None = None

        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.canvas = BalloonCanvas()
        lay.addWidget(self.canvas, 1)
        side = QScrollArea(); side.setWidgetResizable(True); side.setFrameShape(QFrame.NoFrame); side.setFixedWidth(300)
        props = QWidget(); pl = QVBoxLayout(props); pl.setContentsMargins(12, 8, 12, 12)
        side.setWidget(props)
        lay.addWidget(side)

        tools = QHBoxLayout(); tools.setSpacing(6)
        self.undo_btn = QPushButton("Undo"); self.redo_btn = QPushButton("Redo")
        self.fit_page_btn = QPushButton("Fit page")
        self.zoom_label = QLabel("100%"); self.zoom_label.setObjectName("Hint")
        self.undo_btn.setToolTip("Ctrl+Z"); self.redo_btn.setToolTip("Ctrl+Y")
        self.fit_page_btn.setToolTip("Ctrl+0. Ctrl+wheel zooms, the wheel or a middle-drag pans.")
        for w in (self.undo_btn, self.redo_btn, self.fit_page_btn):
            # Compact: the theme's 60 px minimum and wide padding would push the
            # side panel past its 300 px and clip every field below.
            w.setStyleSheet("min-width: 0; padding: 3px 9px;")
            tools.addWidget(w)
        tools.addWidget(self.zoom_label); tools.addStretch()
        pl.addLayout(tools)

        self.empty_hint = QLabel("Add a balloon from the command bar, then drag it into place.\n\n"
                                 "Pink corners resize the body. Blue handles move the tail: "
                                 "the hollow one where it leaves the body, the solid one at the tip.\n\n"
                                 "Tab switches body / tail, arrows nudge (Shift: 5 mm), Delete removes.")
        self.empty_hint.setObjectName("Hint"); self.empty_hint.setWordWrap(True)
        pl.addWidget(self.empty_hint)

        body = QGroupBox("Balloon"); bf = QFormLayout(body)
        self.kind = QComboBox()
        for k in KINDS:
            self.kind.addItem(KIND_LABELS[k], k)
        self.role = QComboBox()
        for r in ROLES:
            self.role.addItem(ROLE_LABELS[r], r)
        self.text = QPlainTextEdit(); self.text.setFixedHeight(84); self.text.setTabChangesFocus(True)
        self.text.setPlaceholderText("What they say. Enter makes a line break.")
        self.auto = QCheckBox("Size the body to the text")
        self.fit_btn = QPushButton("Fit to text")
        bf.addRow("Kind:", self.kind); bf.addRow("Text role:", self.role); bf.addRow(self.text)
        bf.addRow(self.auto); bf.addRow(self.fit_btn)
        self.size_line = QLabel(); self.size_line.setObjectName("Hint"); self.size_line.setWordWrap(True)
        self.size_verdict = QLabel(); self.size_verdict.setObjectName("Verdict"); self.size_verdict.setWordWrap(True)
        bf.addRow(self.size_line); bf.addRow(self.size_verdict)
        pl.addWidget(body)

        tail = QGroupBox("Tail"); tf = QFormLayout(tail)
        self.has_tail = QCheckBox("Has a tail")
        self.base_width = QDoubleSpinBox(); self.base_width.setRange(1, 30); self.base_width.setSingleStep(0.5); self.base_width.setSuffix(" mm")
        self.bend = QSlider(Qt.Horizontal); self.bend.setRange(-100, 100)
        self.follows = QCheckBox("Tip follows body")
        self.aim = QPushButton("Aim base at the tip")
        tf.addRow(self.has_tail); tf.addRow("Base width:", self.base_width); tf.addRow("Bend:", self.bend)
        tf.addRow(self.follows); tf.addRow(self.aim)
        self.tail_box = tail
        pl.addWidget(tail)

        style = QGroupBox("Style"); sf = QFormLayout(style)
        self.stroke_w = QDoubleSpinBox(); self.stroke_w.setRange(0, 3); self.stroke_w.setSingleStep(0.05); self.stroke_w.setDecimals(2); self.stroke_w.setSuffix(" mm")
        self.fill = QComboBox()
        for label, value in FILLS:
            self.fill.addItem(label, value)
        sf.addRow("Stroke width:", self.stroke_w); sf.addRow("Fill:", self.fill)
        pl.addWidget(style)
        pl.addStretch()
        self.groups = (body, tail, style)

        self.canvas.edited.connect(self._canvas_edited)
        self.canvas.gesture_started.connect(self._start_gesture)
        self.canvas.nudged.connect(self._set_nudge_key)
        self.canvas.zoom_changed.connect(lambda z: self.zoom_label.setText(f"{round(z * 100)}%"))
        self.undo_btn.clicked.connect(self.undo); self.redo_btn.clicked.connect(self.redo)
        self.fit_page_btn.clicked.connect(self.canvas.fit)
        QShortcut(QKeySequence.Undo, self, self.undo)
        QShortcut(QKeySequence.Redo, self, self.redo)
        self.undo_btn.setEnabled(False); self.redo_btn.setEnabled(False)
        self.canvas.selected_changed.connect(lambda _n: self._show_selected())
        self.canvas.delete_requested.connect(self.delete_selected)
        self.kind.currentIndexChanged.connect(lambda _: self._field_changed("kind"))
        self.role.currentIndexChanged.connect(lambda _: self._role_changed())
        self.text.textChanged.connect(lambda: self._field_changed("text"))
        self.auto.toggled.connect(lambda _: self._field_changed("auto"))
        self.fit_btn.clicked.connect(self.fit_to_text)
        self.has_tail.toggled.connect(lambda _: self._tail_toggled())
        self.base_width.valueChanged.connect(lambda _: self._field_changed("width"))
        self.bend.valueChanged.connect(lambda _: self._field_changed("bend"))
        self.follows.toggled.connect(lambda _: self._field_changed("follows"))
        self.aim.clicked.connect(self._aim)
        self.stroke_w.valueChanged.connect(lambda _: self._field_changed("stroke"))
        self.fill.currentIndexChanged.connect(lambda _: self._field_changed("fill"))
        self._show_selected()

    # ---------- loading and saving ----------
    def load(self, project: Project, number: int) -> None:
        from cpb_core.svg import read_page
        doc = read_page(project.page_path(number))
        self.project, self.page = project, doc.page
        self.saved = tuple(doc.page.balloons or ())
        self.balloons = list(self.saved)
        self.edited_elsewhere = doc.edited_balloons
        self.undo_stack, self.redo_stack, self._last_key = [], [], None
        self.undo_btn.setEnabled(False); self.redo_btn.setEnabled(False)
        self.canvas.set_page(doc.page, os.path.dirname(project.page_path(number)))
        self.canvas.set_balloons(self.balloons, self.balloons[0].number if self.balloons else None)
        self._show_selected()
        self.dirty_changed.emit(False)

    @property
    def dirty(self) -> bool:
        return self.page is not None and tuple(self.balloons) != self.saved

    def save(self) -> None:
        self.project.save_balloons(self.page.number, self.balloons)
        self.saved = tuple(self.balloons)
        self.edited_elsewhere = []
        self.dirty_changed.emit(False)

    # ---------- balloons ----------
    def selected(self) -> Balloon | None:
        return self.canvas.current()

    def default_font(self, role: str) -> BalloonFont:
        """The role's Lettering preset, or a readable stand-in until there is one."""
        # The UI font as the stand-in: always installed, and plainly a placeholder.
        return default_font_for(self.project, role, self.font().family())

    def add(self, kind: str = "speech", at: QPointF | None = None) -> Balloon:
        """A new balloon in the middle of the selected panel's top half (or the page), tail pointing down."""
        role = DEFAULT_ROLE[kind]
        if at is None:
            live = self.page.geometry().live
            at = QPointF(live.x + live.w / 2, live.y + live.h / 4)
        self._remember(None)
        tail = None if kind == "caption" else Tail(tip_x=round(at.x() - 8, 3), tip_y=round(at.y() + 30, 3))
        text = {"caption": "Meanwhile...", "shout": "HEY!", "thought": "Hmm...", "whisper": "psst..."}.get(kind, "Type here")
        b = fitted(Balloon(number=next_number(self.balloons), kind=kind, cx=round(at.x(), 3), cy=round(at.y(), 3),
                           text=text, role=role, font=self.default_font(role), tail=tail))
        self.balloons.append(b)
        self.canvas.set_balloons(self.balloons, b.number)
        self._after_edit()
        self.text.setFocus(); self.text.selectAll()
        return b

    def delete_selected(self) -> None:
        b = self.selected()
        if b is None:
            return
        self._remember(None)
        i = self.balloons.index(b)
        del self.balloons[i]
        nxt = self.balloons[min(i, len(self.balloons) - 1)].number if self.balloons else None
        self.canvas.set_balloons(self.balloons, nxt)
        self._after_edit()

    def fit_to_text(self) -> None:
        b = self.selected()
        if b is not None:
            self._replace(fitted(replace(b, auto_size=True)))

    # ---------- undo ----------
    def _remember(self, key: str | None) -> None:
        """Save the state before an edit, unless it continues the last one (same key)."""
        if key is not None and key == self._last_key:
            return
        self.undo_stack.append((tuple(self.balloons), self.canvas.selected))
        del self.undo_stack[:-200]   # plenty, and bounded
        self.redo_stack.clear()
        self._last_key = key

    def _start_gesture(self) -> None:
        self._gesture += 1

    def _set_nudge_key(self, key: str) -> None:
        self._nudge_key = key

    def _canvas_edited(self, b: Balloon) -> None:
        key, self._nudge_key = (self._nudge_key or f"drag-{self._gesture}"), None
        self._replace(b, key)

    def _restore(self, state: tuple) -> None:
        balloons, selected = state
        self.balloons = list(balloons)
        self.canvas.set_balloons(self.balloons, selected if any(b.number == selected for b in balloons) else None)
        self._last_key = None
        self._after_edit()

    def undo(self) -> None:
        if self.undo_stack:
            self.redo_stack.append((tuple(self.balloons), self.canvas.selected))
            self._restore(self.undo_stack.pop())

    def redo(self) -> None:
        if self.redo_stack:
            self.undo_stack.append((tuple(self.balloons), self.canvas.selected))
            self._restore(self.redo_stack.pop())

    def _replace(self, b: Balloon, key: str | None = None) -> None:
        if b == self.selected():
            return  # nothing changed (a click without a drag, say): no undo step
        self._remember(key)
        self.balloons = [b if x.number == b.number else x for x in self.balloons]
        self.canvas.set_balloons(self.balloons, b.number)
        self._after_edit()

    def _after_edit(self) -> None:
        self.undo_btn.setEnabled(bool(self.undo_stack)); self.redo_btn.setEnabled(bool(self.redo_stack))
        self._show_selected()
        self.dirty_changed.emit(self.dirty)

    # ---------- inspector ----------
    def _show_selected(self) -> None:
        b = self.selected()
        for g in self.groups:
            g.setEnabled(b is not None)
        self.empty_hint.setVisible(not self.balloons)
        if b is None:
            self.size_line.setText(""); self.size_verdict.setText("")
            self.status_changed.emit()
            return
        self._loading = True
        self.kind.setCurrentIndex(self.kind.findData(b.kind))
        self.role.setCurrentIndex(self.role.findData(b.role))
        if self.text.toPlainText() != b.text:
            self.text.setPlainText(b.text)
        self.auto.setChecked(b.auto_size)
        self.has_tail.setChecked(b.tail is not None)
        self.tail_box.setEnabled(b.kind != "caption")
        for w in (self.base_width, self.bend, self.follows, self.aim):
            w.setEnabled(b.tail is not None)
        if b.tail is not None:
            self.base_width.setValue(b.tail.base_width)
            self.bend.setValue(round(b.tail.bend * 100))
            self.follows.setChecked(b.tail.tip_follows_body)
            self.aim.setEnabled(b.tail.base_angle is not None)
        self.stroke_w.setValue(b.stroke_width)
        self.fill.setCurrentIndex(max(0, self.fill.findData(b.fill)))
        self._loading = False
        # The size check on every balloon (section 9): printed cap height, warning below 1.5 mm.
        cap = cap_height_mm(b.font.size_pt, b.font.cap_ratio)
        role = b.role if b.role != "sfx" else "dialogue"
        kind, sentence = verdict(cap, role)
        self.size_line.setText(f"{b.font.family} {b.font.style} · {b.font.size_pt:g} pt · prints {cap:.2f} mm cap height")
        self.size_verdict.setText(sentence)
        self.size_verdict.setProperty("kind", kind)
        self.size_verdict.style().unpolish(self.size_verdict); self.size_verdict.style().polish(self.size_verdict)
        self.status_changed.emit()

    def _field_changed(self, field: str = "field") -> None:
        b = self.selected()
        if self._loading or b is None:
            return
        kind = self.kind.currentData()
        tail = b.tail
        if tail is not None:
            tail = replace(tail, base_width=self.base_width.value(), bend=self.bend.value() / 100,
                           tip_follows_body=self.follows.isChecked())
        new = replace(b, kind=kind, text=self.text.toPlainText(), auto_size=self.auto.isChecked(), tail=tail,
                      stroke_width=self.stroke_w.value(), fill=self.fill.currentData())
        self._replace(fitted(new), f"{field}-{b.number}")

    def _role_changed(self) -> None:
        b = self.selected()
        if self._loading or b is None:
            return
        role = self.role.currentData()
        self._replace(fitted(replace(b, role=role, font=self.default_font(role))))

    def _tail_toggled(self) -> None:
        b = self.selected()
        if self._loading or b is None:
            return
        if self.has_tail.isChecked():
            tail = Tail(tip_x=round(b.cx - b.rx * 0.3, 3), tip_y=round(b.cy + b.ry * 2.5, 3))
        else:
            tail = None
        self._replace(replace(b, tail=tail))

    def _aim(self) -> None:
        b = self.selected()
        if b is not None and b.tail is not None:
            self._replace(replace(b, tail=replace(b.tail, base_angle=None)))

    def status_text(self) -> str:
        if not self.page:
            return ""
        n = len(self.balloons)
        parts = [f"{n} balloon{'s' if n != 1 else ''}"]
        b = self.selected()
        if b is not None:
            parts.append(f"{KIND_LABELS[b.kind].lower()} {b.number} selected · editing the {self.canvas.part}")
        if self.edited_elsewhere:
            parts.append(f"text of balloon {', '.join(map(str, self.edited_elsewhere))} was changed in another app")
        if self.dirty:
            parts.append("unsaved changes")
        return " · ".join(parts)
