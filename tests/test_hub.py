"""
The hub, driven headlessly (Qt's offscreen platform).

These skip when PySide6 isn't installed, so the core's tests stay
standard-library only. Modal dialogs aren't exec()'d here; the tests build
them and call the same methods their buttons do.
"""

import os
import re
import sys
from dataclasses import replace

import pytest

pytest.importorskip("PySide6.QtWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hub"))

from PySide6.QtCore import QLocale, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from comic_hub import theme  # noqa: E402
from comic_hub.dialogs import BatchDialog, LayoutOptionsDialog, ProjectDialog  # noqa: E402
from comic_hub.lettering_view import CalibrationDialog, FontLibrary, font_for  # noqa: E402
from comic_hub.main_window import MainWindow  # noqa: E402
from comic_hub.widgets import UnitSpinBox  # noqa: E402
from cpb_core.lettering import cap_height_mm, recommend_pt, working_pt  # noqa: E402
from cpb_core.project import create_project, load_project  # noqa: E402
from cpb_core.svg import read_page  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    theme.apply(a)
    return a


@pytest.fixture
def window(app, tmp_path):
    project = create_project(str(tmp_path / "My Comic"), "My Comic", blank_pages=4, seed=3)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(settings, FontLibrary(settings, cache_path=str(tmp_path / "font-cache.json")))
    w.resize(1240, 820)
    w.show()
    w.open_project(project.folder, quiet=True)
    app.processEvents()
    yield w
    w.builder.saved = w.builder.draft  # nothing to ask about on close
    w.balloons_view.saved = tuple(w.balloons_view.balloons)
    w.close()


# ---------- balloons (M5) ----------
def test_balloons_add_edit_and_save(window, app):
    from PySide6.QtCore import QPointF
    window.selected = 2
    window.go("balloons")
    v = window.balloons_view
    assert window.view == "balloons" and v.balloons == []
    window.add_balloon("speech")
    b = v.selected()
    assert b.kind == "speech" and b.lines and b.tail is not None
    v.text.setPlainText("WHERE IS THE MAP?")
    assert v.selected().text == "WHERE IS THE MAP?"
    assert v.dirty and "*" in window.windowTitle()
    # Drag the tip somewhere else: the body stays.
    c = v.canvas
    body = (v.selected().cx, v.selected().cy)
    tip_px = c.to_px(QPointF(b.tail.tip_x, b.tail.tip_y))
    c._drag = ("tip", c.to_mm(tip_px), v.selected())
    target = c.to_px(QPointF(b.tail.tip_x + 10, b.tail.tip_y))
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, Qt
    c.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, target, target, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    moved = v.selected()
    assert (moved.cx, moved.cy) == body and moved.tail.tip_x == pytest.approx(b.tail.tip_x + 10, abs=0.01)
    assert window.save_letters() and not v.dirty
    saved = read_page(window.project.page_path(2)).page.balloons
    assert [x.text for x in saved] == ["WHERE IS THE MAP?"]


def test_balloon_undo_groups_drags_typing_and_nudges(window, app):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    window.selected = 1
    window.go("balloons")
    v = window.balloons_view
    assert not v.undo_btn.isEnabled()
    v.add("speech")
    c = v.canvas
    added = v.selected()
    # A drag in several moves is one step.
    c.gesture_started.emit()
    start = c.to_px(QPointF(added.cx, added.cy))
    c._drag = ("body", c.to_mm(start), added)
    for dx in (5, 10, 20):
        p = start + QPointF(dx, 0)
        c.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, p, p, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    c._drag = None
    dragged = v.selected()
    assert dragged.cx > added.cx
    # Typing is one step; a run of nudges is one step.
    v.text.setPlainText("A"); v.text.setPlainText("AB"); v.text.setPlainText("ABC")
    for _ in range(3):
        c.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
    assert v.selected().cx == pytest.approx(dragged.cx + 1.5)
    v.undo()   # the nudges
    assert v.selected().cx == pytest.approx(dragged.cx) and v.selected().text == "ABC"
    v.undo()   # the typing
    assert v.selected().text == added.text
    v.undo()   # the drag
    assert v.selected().cx == pytest.approx(added.cx)
    v.undo()   # the add
    assert v.balloons == [] and not v.undo_btn.isEnabled()
    v.redo(); v.redo()
    assert v.selected().cx == pytest.approx(dragged.cx)


def test_balloon_canvas_zooms_around_the_cursor(window, app):
    from PySide6.QtCore import QPointF
    window.selected = 1
    window.go("balloons")
    c = window.balloons_view.canvas
    c.resize(600, 800)
    spot = QPointF(200, 300)
    held = c.to_mm(spot)
    c.zoom_to(3.0, spot)
    assert c.zoom == 3.0
    after = c.to_px(held)
    assert after.x() == pytest.approx(spot.x(), abs=0.01) and after.y() == pytest.approx(spot.y(), abs=0.01)
    c.zoom_to(100)
    assert c.zoom == 12.0   # capped
    c.fit()
    assert c.zoom == 1.0 and c.pan == QPointF(0, 0)


def test_balloon_keyboard_and_resize(window, app):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    window.selected = 1
    window.go("balloons")
    v = window.balloons_view
    v.add("thought")
    c = v.canvas
    b = v.selected()
    key = lambda k, mod=Qt.NoModifier: c.keyPressEvent(QKeyEvent(QEvent.KeyPress, k, mod))
    key(Qt.Key_Right, Qt.ShiftModifier)
    assert v.selected().cx == pytest.approx(b.cx + 5) and v.selected().tail.tip_x == b.tail.tip_x  # tip stays
    key(Qt.Key_Tab)
    assert c.part == "tail"
    key(Qt.Key_Down)
    assert v.selected().tail.tip_y == pytest.approx(b.tail.tip_y + 0.5)
    # Resizing turns auto-size off; Fit to text turns it back on.
    v._replace(replace(v.selected(), rx=40, ry=30, auto_size=False))
    assert not v.auto.isChecked()
    v.fit_to_text()
    assert v.selected().auto_size and v.selected().rx < 40
    key(Qt.Key_Delete)
    assert v.balloons == []
    v.saved = tuple(v.balloons)


def test_builder_save_keeps_the_balloons(window, app):
    window.selected = 3
    window.go("balloons")
    window.add_balloon("caption")
    window.save_letters()
    window.go("builder")
    window.builder.gutter.set_mm(6); window.builder._changed()
    assert window.save_page()
    assert len(read_page(window.project.page_path(3)).page.balloons) == 1


# ---------- drawn pages (M5, D7) ----------
def _art_png(path, w=850, h=1300, dpi=150):
    from PySide6.QtGui import QColor, QImage, QPainter
    img = QImage(w, h, QImage.Format_RGB32); img.fill(QColor("#f4e1c1"))
    p = QPainter(img); p.fillRect(40, 40, w // 2, h // 3, QColor("#3a6ea5")); p.end()
    img.setDotsPerMeterX(round(dpi / 0.0254)); img.setDotsPerMeterY(round(dpi / 0.0254))
    img.save(str(path))
    return str(path)


def _pdf(path, pages=2):
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    w = QPdfWriter(str(path))
    w.setPageSize(QPageSize(QSizeF(150, 220), QPageSize.Millimeter)); w.setPageMargins(QMarginsF(0, 0, 0, 0))
    p = QPainter(w)
    for i in range(pages):
        if i:
            w.newPage()
        p.drawText(200, 400, f"PAGE {i + 1}")
    p.end()
    return str(path)


def test_import_drawn_images_and_pdf_pages(window, app, tmp_path):
    from comic_hub import pdf_art
    from comic_hub.art_import import ImportArtDialog
    files = [_art_png(tmp_path / "scan.png")]
    if pdf_art.available():
        files.append(_pdf(tmp_path / "book.pdf"))
    dlg = ImportArtDialog(window.project, window, files)
    dlg.dpi.setValue(150)
    assert dlg.list.count() == 1 + (2 if pdf_art.available() else 0)
    dlg.run()
    assert [p.number for p in dlg.made] == list(range(5, 5 + dlg.list.count()))
    first = window.project.load_page(5)
    assert first.is_art and first.size.trim_w == pytest.approx(850 * 25.4 / 150, abs=0.01)
    if pdf_art.available():
        pdf_page = window.project.load_page(6)
        assert pdf_page.size.trim_w == pytest.approx(150, abs=0.3)  # the PDF's real size
    # Drawn pages skip the builder and open in Balloons, art underneath.
    window.selected = 5
    window.go("builder")
    assert window.view == "balloons" and window.balloons_view.canvas.folder
    window.add_balloon("speech")
    assert window.save_letters()
    assert window.project.load_page(5).art == first.art


# ---------- hand-cut layouts (prototype) ----------
def _drag(canvas, a_mm, b_mm, mods=None):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    mods = mods or Qt.NoModifier
    a, b = canvas.to_px(*a_mm), canvas.to_px(*b_mm)
    canvas.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, a, a, Qt.LeftButton, Qt.LeftButton, mods))
    canvas.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, b, b, Qt.LeftButton, Qt.LeftButton, mods))
    canvas.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, b, b, Qt.LeftButton, Qt.NoButton, mods))


def test_cut_merge_and_inset_by_hand(window, app):
    window.selected = 1
    window.go("builder")
    b = window.builder
    assert b.draft.layout["kind"] == "manual" and len(b.draft.panels()) == 1  # the wizard's blank pages are blank
    c = b.preview
    assert c.tool == "select"
    b.set_tool("knife")
    live = b.draft.geometry().live
    mid_y = live.y + live.h / 2
    # A nearly level drag snaps to straight across.
    _drag(c, (live.x + 10, mid_y), (live.right - 10, mid_y + 2))
    top, bottom = b.draft.panels()
    assert top.points[2][1] == pytest.approx(top.points[3][1])
    # A slanted cut in the bottom panel, with snapping off.
    from PySide6.QtCore import Qt
    _drag(c, (live.x + 60, mid_y + 10), (live.x + 80, live.bottom - 10), Qt.AltModifier)
    assert len(b.draft.panels()) == 3 and b.dirty
    b.set_tool("inset")
    _drag(c, (live.x + 20, live.y + 20), (live.x + 70, live.y + 60))
    assert sum(p.on_top for p in b.draft.panels()) == 1
    b.undo()
    assert len(b.draft.panels()) == 3
    b.redo()
    b.set_tool("merge")
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    pos = c.to_px(live.x + live.w * 0.9, mid_y)  # on the first cut's gutter
    c.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, pos, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    assert len(b.draft.panels()) == 2  # the cut inside the bottom half went with it; the inset stays
    assert window.save_page()
    assert len(read_page(window.project.page_path(1)).page.panels()) == 2


def test_slide_gutters_and_edit_insets_with_select(window, app):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    window.selected = 3
    window.go("builder")
    b = window.builder
    c = b.preview
    live = b.draft.geometry().live
    b.set_tool("knife")
    # Ctrl puts the cut through the middle, wherever you drag it.
    _drag(c, (live.x + 5, live.y + 20), (live.right - 5, live.y + 21), Qt.ControlModifier)
    top, bottom = b.draft.panels()
    assert top.rect.h == pytest.approx(bottom.rect.h, abs=0.01)
    undo_depth = len(b.undo_stack)
    # Slide the gutter down 20 mm: one drag, one undo step.
    b.set_tool("select")
    y = live.y + live.h / 2
    _drag(c, (live.x + 40, y), (live.x + 40, y + 20))
    top2, bottom2 = b.draft.panels()
    assert top2.rect.h == pytest.approx(top.rect.h + 20, abs=0.05) and len(b.undo_stack) == undo_depth + 1
    # Draw an inset, cut it, move it, resize it, delete it.
    b.set_tool("inset")
    _drag(c, (live.x + 20, live.y + 20), (live.x + 80, live.y + 60))
    b.set_tool("knife")
    _drag(c, (live.x + 50, live.y + 15), (live.x + 50, live.y + 65), Qt.AltModifier)
    insets = [p for p in b.draft.panels() if p.on_top]
    assert len(insets) == 2
    b.set_tool("select")
    _drag(c, (live.x + 30, live.y + 40), (live.x + 40, live.y + 50))
    moved = [p for p in b.draft.panels() if p.on_top]
    assert moved[0].rect.x == pytest.approx(insets[0].rect.x + 10, abs=0.05) and len(moved) == 2
    _drag(c, (live.x + 90, live.y + 70), (live.x + 110, live.y + 70))   # the right-middle handle
    wider = [p for p in b.draft.panels() if p.on_top]
    assert max(p.rect.right for p in wider) == pytest.approx(live.x + 110, abs=0.05)
    c.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert not any(p.on_top for p in b.draft.panels())
    b.saved = b.draft


def test_restore_project_defaults_and_undo_it(window, app):
    window.selected = 4
    window.go("builder")
    b = window.builder
    original = b.draft
    assert not b.restore_btn.isEnabled()
    b.gutter.set_mm(7); b.margin.set_mm(15); b._changed()
    assert b.restore_btn.isEnabled() and b.draft.gutter == 7
    b.restore_defaults()
    assert b.draft == original and b.gutter.mm() == original.gutter and not b.restore_btn.isEnabled()
    b.undo()
    assert b.draft.gutter == 7 and b.gutter.mm() == 7 and b.margin.mm() == 15


def test_presets_can_be_cut_further(window, app):
    window.selected = 2
    window.go("builder")
    b = window.builder
    dlg = LayoutOptionsDialog(b.draft, window)
    assert dlg.tabs.tabText(0) == "Presets"
    dlg.changed.connect(b.set_draft)
    dlg._preset_clicked(dlg.presets.item(0))
    n = len(b.draft.panels())
    p = b.draft.panels()[0].rect
    b.set_tool("knife")
    _drag(b.preview, (p.x + 5, p.y + p.h / 2), (p.right - 5, p.y + p.h / 2 + 8))
    assert b.draft.layout["kind"] == "manual" and len(b.draft.panels()) == n + 1


def test_unit_spin_box_never_changes_the_stored_value(app):
    box = UnitSpinBox(168.0, 20, 1000)
    for unit in ("in", "cm", "mm", "in"):
        box.set_unit(unit)
        assert box.mm() == 168.0
    box.set_unit("cm")
    box.setValue(21.0)  # typing 21 cm
    assert box.mm() == pytest.approx(210.0)


@pytest.mark.parametrize("typed", ["3,5", "3.5", "3.5 mm"])
def test_unit_spin_box_takes_a_dot_under_a_comma_locale(app, typed):
    # On a Spanish Windows the box shows "3,5 mm", but the numpad types a dot.
    box = UnitSpinBox(1.0, 0, 50)
    box.setLocale(QLocale(QLocale.Spanish, QLocale.Spain))
    box.lineEdit().selectAll()
    box.lineEdit().insert(typed)
    box.interpretText()
    assert box.mm() == pytest.approx(3.5)


def test_window_starts_inside_the_screen(app, tmp_path):
    # 1240 × 820 is taller than a 1080p screen at 150 % scaling; the title bar must stay reachable.
    w = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    area = w.screen().availableGeometry()
    assert w.height() <= area.height()
    assert w.frameGeometry().top() >= area.top()


def test_opening_a_project_shows_its_pages(window):
    assert window.view == "pages"
    assert sum(lw.count() for lw in window.pages_view.lists.values()) == 4 + 1  # 4 pages + the Add page tile
    assert "Pages · My Comic" in window.windowTitle()


def test_build_a_page_from_the_ui(window, app):
    """M3's done-when: edit a page in the builder and save it."""
    window.selected = 2
    window.go("builder")
    b = window.builder
    b.gutter.set_mm(5); b.radius.set_mm(2); b._changed()
    assert b.dirty and "*" in window.windowTitle()
    dlg = LayoutOptionsDialog(b.draft, window)
    dlg.changed.connect(b.set_draft)
    dlg.panels.setValue(6)
    dlg.accept()
    assert window.save_page()
    assert not b.dirty and "*" not in window.windowTitle()
    page = read_page(window.project.page_path(2)).page
    assert (len(page.cells), page.gutter, page.style.corner_radius) == (6, 5.0, 2.0)


def test_switching_units_doesnt_change_the_page(window):
    window.selected = 1
    window.go("builder")
    before = window.builder.draft
    for unit in ("in", "cm", "mm"):
        button = next(x for x in window.builder.unit_group.buttons() if x.property("unit") == unit)
        button.setChecked(True)
        window.builder._unit_changed(button)
    assert window.builder.draft == before and not window.builder.dirty


def test_layout_dialog_cancel_puts_the_page_back(window):
    window.selected = 1
    window.go("builder")
    original = window.builder.draft
    dlg = LayoutOptionsDialog(original, window)
    dlg.changed.connect(window.builder.set_draft)
    dlg._roll()
    assert window.builder.draft != original
    dlg.reject()
    assert window.builder.draft == original


def test_batch_dialog_generates_pages_and_continues_numbering(window):
    dlg = BatchDialog(window.project, window.selected, window)
    dlg.count.setValue(3)
    assert dlg.strip.count() == 3  # the preview shows what you'll get
    dlg._generate()
    assert [p.number for p in dlg.made] == [5, 6, 7]
    assert [e.number for e in load_project(window.project.folder).pages] == [1, 2, 3, 4, 5, 6, 7]


def test_status_change_from_the_details_pane(window):
    window.pages_view.selected = 3
    window.pages_view._set_status(3, "inks")
    assert load_project(window.project.folder).entry(3).status == "inks"
    assert window.pages_view.lists["inks"].count() == 1


def test_project_dialog_values_and_settings_mode(window, tmp_path):
    new = ProjectDialog(window)
    new.name.setText("Zine"); new._name_to_folder("Zine")
    new.paper.setCurrentText("ISO A5")
    v = new.values()
    assert v["name"] == "Zine" and v["folder"].endswith("Zine")
    assert (v["size"].trim_w, v["size"].trim_h) == (148, 210)
    settings = ProjectDialog(window, window.project)
    assert settings.settings_mode and settings.name.text() == "My Comic"
    assert settings.folder.isReadOnly()


def test_recent_projects_and_reopen(window, app, tmp_path):
    assert window.recent() == [window.project.folder]
    again = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    assert again.project is not None and again.project.name == "My Comic"
    again.close()


def test_back_and_forward(window):
    window.go("projects")
    window.go_back()
    assert window.view == "pages"
    window.go_forward()
    assert window.view == "projects"


# ---------- M4: lettering ----------
@pytest.fixture
def lettering(window):
    window.go("lettering")
    lib = window.lettering.library
    if not lib.entries:
        pytest.skip("no fonts installed on this machine")
    return window.lettering


def test_lettering_recommends_a_size_and_saves_the_preset(window, lettering):
    """M4's done-when, second half: presets saved."""
    lettering.table.selectRow(0)
    e = lettering.entry
    rec = recommend_pt(e.cap_ratio, "dialogue")
    assert lettering.size() == rec and lettering.big.text() == f"{rec:g} pt"
    lettering._size_changed(rec - 2)
    assert lettering.verdict.property("kind") in ("small", "bad")
    lettering._use_recommended()
    assert lettering.verdict.property("kind") == "good"
    lettering._save_preset()
    saved = load_project(window.project.folder).lettering["dialogue"]
    assert (saved.family, saved.style, saved.size_pt) == (e.info.family, e.info.style, rec)
    assert "Lettering" in window.windowTitle() and e.info.family in window.status.text()


def test_working_size_follows_the_projects_scale(window, lettering):
    lettering.table.selectRow(0)
    lettering.scale.setCurrentIndex(2)  # drawing at 3×
    assert load_project(window.project.folder).work_scale == 3
    assert f"type {working_pt(lettering.size(), 3):g} pt" in lettering.cap_line.text()


def test_font_search_and_favourites(window, lettering):
    first = lettering.library.entries[0]
    assert window.search.placeholderText() == "Search fonts"
    window.search.setText(first.info.family[:4])
    assert lettering._rows and all(first.info.family[:4].lower() in f"{e.info.family} {e.info.style}".lower()
                                   for e in lettering._rows)
    window.search.clear()
    lettering._cell_clicked(0, 0)  # the star column
    window.favourites_only(True)
    assert [e.key for e in lettering._rows] == [lettering.library.entries[0].key]
    window.favourites_only(False)
    window.go("pages")  # the search box goes back to pages, empty
    assert window.search.placeholderText() == "Search pages" and window.search.text() == ""


def test_calibration_sheet_prints_at_real_size(window, lettering, tmp_path):
    """M4's done-when, first half: the sheet for the test print."""
    lettering.table.selectRow(0)
    dlg = CalibrationDialog(lettering, window)
    assert dlg.chosen() == [lettering.entry]  # the font on screen is ticked
    path = str(tmp_path / "sheet.pdf")
    dlg.write_pdf(dlg.sheet(), path)
    data = open(path, "rb").read()
    box = re.search(rb"/MediaBox \[\s*0 0 ([\d.]+) ([\d.]+)\s*\]", data)
    # A4 is 595.28 × 841.89 pt; Qt writes PostScript's whole-point A4, which is how printers recognise the paper.
    assert box and (float(box[1]), float(box[2])) == pytest.approx((595.28, 841.89), abs=0.5)
    assert b"/FontFile2" in data or b"/FontFile3" in data  # the fonts travel with the PDF

    # After the test print: type the code of the best sample.
    dlg.code.setText("a5")
    assert dlg.use.isEnabled()
    sample = dlg.sheet().sample("A5")
    dlg._use()
    saved = load_project(window.project.folder).lettering["dialogue"]
    assert saved.size_pt == sample.size_pt and lettering.size() == sample.size_pt
    again = CalibrationDialog(lettering, window)  # the next sheet starts from the last one
    assert again.chosen() == [lettering.entry]


def test_unknown_sample_code_is_refused(window, lettering):
    lettering.table.selectRow(0)
    dlg = CalibrationDialog(lettering, window)
    dlg.code.setText("Z9")
    assert not dlg.use.isEnabled() and "No sample" in dlg.meaning.text()


def test_pdf_text_has_the_physical_cap_height(lettering, tmp_path):
    """What the advisor promises is what the PDF draws: 8 pt caps measure cap_ratio × 8 pt."""
    from PySide6.QtGui import QFontMetricsF, QPdfWriter
    writer = QPdfWriter(str(tmp_path / "m.pdf"))
    writer.setResolution(1200)
    for e in lettering.library.entries[:5]:
        cap = QFontMetricsF(font_for(e.info, 8.0), writer).capHeight() / (1200 / 25.4)
        assert cap == pytest.approx(cap_height_mm(8.0, e.cap_ratio), abs=0.05)


# ---------- script (M7) ----------
def test_script_screen_reads_links_and_makes_balloons(window, app, tmp_path):
    from PySide6.QtCore import Qt
    src = tmp_path / "my script.txt"
    src.write_text("PAGE 1\nPANEL 1\nBackground: rain.\nMARA: Did you see that?\nSFX: BANG\n"
                   "PAGE 2\nPANEL 1\nCAPTION: Later.\n", encoding="utf-8")
    window.go("script")
    v = window.script_view
    assert window.view == "script" and v.script is None and not v.make_btn.isEnabled()
    assert v.load_file(str(src))
    # Copied into the project and linked; the stage note's first guess is "not a speaker".
    assert os.path.exists(os.path.join(window.project.folder, "script", "my script.txt"))
    assert window.project.script["not_speakers"] == ["background"]
    keys = {v.speakers.item(i).data(Qt.UserRole): v.speakers.item(i).checkState() for i in range(v.speakers.count())}
    assert keys == {"background": Qt.Unchecked, "mara": Qt.Checked, "caption": Qt.Checked}
    v.make()
    saved = read_page(window.project.page_path(1)).page.balloons
    assert [b.text for b in saved] == ["Did you see that?"]
    assert read_page(window.project.page_path(2)).page.balloons[0].kind == "caption"
    assert "BANG" in v.result.text() and window.selected == 1
    # Ticking a label in the list makes its lines balloons next time (here: added to the page).
    item = next(v.speakers.item(i) for i in range(v.speakers.count()) if v.speakers.item(i).data(Qt.UserRole) == "background")
    item.setCheckState(Qt.Checked)
    assert window.project.script["not_speakers"] == []
    v.existing.setCurrentIndex(1)
    v.make()
    assert [b.text for b in read_page(window.project.page_path(1)).page.balloons] == ["Did you see that?", "rain.", "Did you see that?"]
    # The link survives reopening the screen.
    window.go("pages"); window.go("script")
    assert v.script is not None and v.path.endswith("my script.txt")
