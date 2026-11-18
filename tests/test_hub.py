"""
The hub, driven headlessly (Qt's offscreen platform).

These skip when PySide6 isn't installed, so the core's tests stay
standard-library only. Modal dialogs aren't exec()'d here; the tests build
them and call the same methods their buttons do.
"""

import os
import sys

import pytest

pytest.importorskip("PySide6.QtWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hub"))

from PySide6.QtCore import QLocale, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from comic_hub import theme  # noqa: E402
from comic_hub.dialogs import BatchDialog, LayoutOptionsDialog, ProjectDialog  # noqa: E402
from comic_hub.main_window import MainWindow  # noqa: E402
from comic_hub.widgets import UnitSpinBox  # noqa: E402
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
    w = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    w.resize(1240, 820)
    w.show()
    w.open_project(project.folder, quiet=True)
    app.processEvents()
    yield w
    w.builder.saved = w.builder.draft  # nothing to ask about on close
    w.close()


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
