"""The main window: address bar, command bar, navigation pane, screens, status bar."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QStackedWidget,
    QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from cpb_core.project import Project, create_project, load_project, update_settings

from . import icons, theme
from .dialogs import AddPageDialog, BatchDialog, LayoutOptionsDialog, ProjectDialog
from .balloons_view import KIND_LABELS, BalloonsView
from .lettering_view import CalibrationDialog, FontLibrary, LetteringView
from .views import BuilderView, PagesView, PlaceholderView, ProjectsView
from .widgets import Toast
from .winframe import tint_title_bar

ORG, APP = "Antares", "Comic Hub"
MAX_RECENT = 12

NAV = [  # (group, [(view, label, icon)])
    ("Projects", [("projects", "All projects", "projects")]),
    ("@project", [("pages", "Pages", "pages"), ("builder", "Page builder", "builder"),
                  ("balloons", "Balloons", "balloon"), ("lettering", "Lettering", "type")]),
    ("Project", [("settings", "Project settings…", "gear"), ("script", "Script", "folder"), ("exports", "Exports", "send")]),
]
SOON = {
    "script": ("Script view arrives in M7", "Link your comic script and see which pages each scene covers."),
    "exports": ("Exports", "For now, run the importers in Photoshop and Illustrator (see importers/README.md). Sending from the hub comes later."),
}


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None, fonts: FontLibrary | None = None):
        super().__init__()
        self.settings = settings or QSettings(ORG, APP)
        self.project: Project | None = None
        self.selected: int | None = None
        self.view = "projects"
        self.back_stack: list[str] = []
        self.fwd_stack: list[str] = []
        self.setWindowTitle("Comic Hub")
        self.resize(1240, 820)
        self._fit_to_screen()

        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central); outer.setContentsMargins(7, 4, 7, 7); outer.setSpacing(6)

        # Address row: back, forward, breadcrumb, search.
        addr = QHBoxLayout(); addr.setSpacing(6)
        self.back_btn = self._round("left", "Back", self.go_back)
        self.fwd_btn = self._round("right", "Forward", self.go_forward)
        self.crumb = QLabel(); self.crumb.setObjectName("Crumb")
        self.search = QLineEdit(); self.search.setObjectName("Search"); self.search.setPlaceholderText("Search pages")
        self.search.setFixedWidth(220); self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", theme.MUTED), QLineEdit.TrailingPosition)
        self.search.textChanged.connect(self._search)
        for w in (self.back_btn, self.fwd_btn):
            addr.addWidget(w)
        addr.addWidget(self.crumb, 1); addr.addWidget(self.search)
        outer.addLayout(addr)

        # Client area: command bar, then navigation pane + screens.
        client = QFrame(); client.setObjectName("Client")
        cl = QVBoxLayout(client); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        self.cmdbar = QToolBar(); self.cmdbar.setObjectName("CommandBar"); self.cmdbar.setMovable(False)
        self.cmdbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        cl.addWidget(self.cmdbar)
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        self.nav = QTreeWidget(); self.nav.setObjectName("NavPane"); self.nav.setHeaderHidden(True)
        self.nav.setFixedWidth(200); self.nav.setIndentation(14); self.nav.setRootIsDecorated(False)
        self.nav.itemClicked.connect(self._nav_clicked)
        body.addWidget(self.nav)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        cl.addLayout(body, 1)
        outer.addWidget(client, 1)

        self.projects_view = ProjectsView()
        self.projects_view.open_requested.connect(self.open_project)
        self.projects_view.settings_requested.connect(self.project_settings)
        self.projects_view.go_pages.connect(lambda: self.go("pages"))
        self.pages_view = PagesView()
        self.pages_view.selection_changed.connect(self._select)
        self.pages_view.open_requested.connect(lambda n: (self._select(n), self.go("builder")))
        self.pages_view.add_requested.connect(self.add_page)
        self.builder = BuilderView()
        self.builder.dirty_changed.connect(lambda _: self._update_title())
        self.lettering = LetteringView(self.settings, fonts)
        self.lettering.status_changed.connect(self._update_title)
        self.balloons_view = BalloonsView()
        self.balloons_view.dirty_changed.connect(lambda _: self._update_title())
        self.balloons_view.status_changed.connect(self._update_title)
        self.views = {"projects": self.projects_view, "pages": self.pages_view, "builder": self.builder,
                      "balloons": self.balloons_view, "lettering": self.lettering}
        for key, (title, text) in SOON.items():
            self.views[key] = PlaceholderView(title, text)
        for w in self.views.values():
            self.stack.addWidget(w)

        self.status = QLabel(); self.statusBar().addWidget(self.status, 1)
        self.toast_widget = Toast(self)
        self._build_nav()
        self._reopen_last()

    # ---------- small helpers ----------
    def _round(self, icon: str, tip: str, slot) -> QToolButton:
        b = QToolButton(); b.setObjectName("RoundButton"); b.setIcon(icons.icon(icon, theme.ACCENT_TEXT, 14))
        b.setToolTip(tip); b.clicked.connect(slot)
        return b

    def _fit_to_screen(self) -> None:
        """Start no bigger than the screen's free area, and centred in it.

        Sizes are in logical pixels, so at 125 % and 150 % display scaling
        1240 × 820 needs 1550 × 1025 and 1860 × 1230 real pixels: taller than a
        1080p screen. Windows then pushes the title bar above the top edge,
        where it can't be grabbed to move the window.
        """
        area = self.screen().availableGeometry()  # the screen minus the taskbar
        self.winId()  # makes the native window now, so Qt knows how big the title bar and borders are
        m = self.windowHandle().frameMargins()
        w = min(self.width(), area.width() - m.left() - m.right())
        h = min(self.height(), area.height() - m.top() - m.bottom())
        self.resize(w, h)
        # move() places the outside of the frame, so centre the frame, not just the client area.
        self.move(area.x() + (area.width() - w - m.left() - m.right()) // 2,
                  area.y() + (area.height() - h - m.top() - m.bottom()) // 2)

    def toast(self, title: str, text: str) -> None:
        self.toast_widget.show_message(title, text)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        tint_title_bar(self)

    # ---------- recent projects ----------
    def recent(self) -> list[str]:
        value = self.settings.value("recent", [])
        folders = [value] if isinstance(value, str) else list(value or [])
        return [f for f in folders if os.path.isdir(f)]

    def _remember(self, folder: str) -> None:
        folders = [folder] + [f for f in self.recent() if os.path.normcase(f) != os.path.normcase(folder)]
        self.settings.setValue("recent", folders[:MAX_RECENT])
        self.settings.setValue("last", folder)

    def _reopen_last(self) -> None:
        last = self.settings.value("last", "")
        if last and os.path.isdir(last):
            try:
                self.open_project(last, quiet=True)
                return
            except ValueError:
                pass
        self.go("projects", record=False)

    # ---------- navigation ----------
    def _build_nav(self) -> None:
        self.nav.clear()
        self._nav_items = {}
        for group, items in NAV:
            title = self.project.name if group == "@project" and self.project else ("My Comic" if group == "@project" else group)
            head = QTreeWidgetItem([title]); head.setIcon(0, icons.icon("star", theme.ACCENT))
            head.setFlags(Qt.ItemIsEnabled)
            f = head.font(0); f.setBold(True); head.setFont(0, f)
            self.nav.addTopLevelItem(head)
            for key, label, ic in items:
                it = QTreeWidgetItem([label]); it.setIcon(0, icons.icon(ic, theme.ACCENT)); it.setData(0, Qt.UserRole, key)
                if key in SOON and key != "exports":
                    it.setToolTip(0, SOON[key][0])
                head.addChild(it)
                self._nav_items[key] = it
            head.setExpanded(True)

    def _nav_clicked(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.UserRole)
        if key == "settings":
            self.project_settings()
            self._sync_nav()
        elif key:
            self.go(key)

    def _sync_nav(self) -> None:
        it = self._nav_items.get(self.view)
        if it:
            self.nav.setCurrentItem(it)

    def go(self, view: str, record: bool = True) -> None:
        if view in ("pages", "builder", "balloons", "lettering") and not self.project:
            view = "projects"
        if view in ("builder", "balloons") and self.selected is None:
            self.toast("No page selected", "Pick a page in Pages first, or add one.")
            view = "pages"
        if self.view != view and not self._leave_editor():
            self._sync_nav()
            return
        if record and view != self.view:
            self.back_stack.append(self.view)
            self.fwd_stack.clear()
        searched = self._search_context()
        self.view = view
        if self._search_context() != searched:
            self._reset_search()
        if view == "projects":
            self.projects_view.set_projects(self.recent(), self.project.folder if self.project else None)
        elif view == "pages":
            self.pages_view.set_project(self.project, self.selected)
        elif view == "builder":
            try:
                self.builder.load(self.project, self.selected)
            except (ValueError, OSError) as e:
                QMessageBox.warning(self, "Can't open the page", f"page_{self.selected:02d} can't be read: {e}.")
                return self.go("pages", record=False)
        elif view == "balloons":
            try:
                self.balloons_view.load(self.project, self.selected)
            except (ValueError, OSError) as e:
                QMessageBox.warning(self, "Can't open the page", f"page_{self.selected:02d} can't be read: {e}.")
                return self.go("pages", record=False)
            if self.balloons_view.edited_elsewhere:
                n = self.balloons_view.edited_elsewhere
                self.toast("Text changed in another app",
                           f"Balloon{'s' if len(n) > 1 else ''} {', '.join(map(str, n))}: the words from the file are kept.")
        elif view == "lettering":
            self.lettering.set_project(self.project)
        self.stack.setCurrentWidget(self.views[view])
        self.back_btn.setEnabled(bool(self.back_stack)); self.fwd_btn.setEnabled(bool(self.fwd_stack))
        self._sync_nav()
        self._build_commands()
        self._update_title()

    def go_back(self) -> None:
        if self.back_stack:
            target = self.back_stack.pop()
            self.fwd_stack.append(self.view)
            self.go(target, record=False)

    def go_forward(self) -> None:
        if self.fwd_stack:
            target = self.fwd_stack.pop()
            self.back_stack.append(self.view)
            self.go(target, record=False)

    def _leave_editor(self) -> bool:
        """Leaving the builder or the balloon editor: ask about unsaved changes. True means it's OK to leave."""
        if self.view == "builder":
            return self._leave_builder()
        if self.view == "balloons":
            return self._leave_balloons()
        return True

    def _ask_to_save(self, what: str) -> str:
        """'save', 'discard' or 'cancel'."""
        box = QMessageBox(QMessageBox.Question, "Unsaved changes", what, parent=self)
        save = box.addButton("Save", QMessageBox.AcceptRole)
        box.addButton("Don't save", QMessageBox.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        return "cancel" if box.clickedButton() is cancel else "save" if box.clickedButton() is save else "discard"

    def _leave_balloons(self) -> bool:
        if not self.balloons_view.dirty:
            return True
        answer = self._ask_to_save(f"Save the balloons on page_{self.balloons_view.page.number:02d}?")
        if answer == "save":
            return self.save_letters()
        return answer == "discard"

    def _leave_builder(self) -> bool:
        """Ask before throwing away unsaved builder changes. True means it's OK to leave."""
        if not self.builder.dirty:
            return True
        box = QMessageBox(QMessageBox.Question, "Unsaved changes",
                          f"Save the changes to page_{self.builder.draft.number:02d}?", parent=self)
        save = box.addButton("Save", QMessageBox.AcceptRole)
        box.addButton("Don't save", QMessageBox.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is cancel:
            return False
        if box.clickedButton() is save:
            return self.save_page()
        return True

    def _select(self, number: int) -> None:
        self.selected = number
        self._update_title()

    # The search box looks through what's on screen: fonts on Lettering, pages everywhere else.
    def _search_context(self) -> str:
        return "fonts" if self.view == "lettering" else "pages"

    def _reset_search(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.search.setPlaceholderText("Search fonts" if self._search_context() == "fonts" else "Search pages")
        if self.pages_view.filter:
            self.pages_view.filter = ""
            self.pages_view.refresh()
        if self.lettering.filter:
            self.lettering.filter = ""
            self.lettering.refresh_table()

    def _search(self, text: str) -> None:
        if self._search_context() == "fonts":
            self.lettering.filter = text
            self.lettering.refresh_table()
            return
        if self.view != "pages" and text:
            self.go("pages")
        self.pages_view.filter = text
        self.pages_view.refresh()

    # ---------- command bar ----------
    def _build_commands(self) -> None:
        bar = self.cmdbar
        bar.clear()
        cmds = {
            "projects": [("plus", "New project…", self.new_project, True), ("open", "Open…", self.open_dialog, False),
                         ("gear", "Project settings…", self.project_settings, False)],
            "pages": [("plus", "Add page…", self.add_page, True), ("stack", "Batch generate…", self.batch, True), None,
                      ("builder", "Open in builder", lambda: self.go("builder"), False)],
            "builder": [("sliders", "Layout options…", self.layout_options, False), ("dice", "Roll layout", self.roll, False),
                        ("check", "Save page", self.save_page, True)],
            "balloons": [("balloon", "Add balloon", None, True), ("trash", "Delete balloon", self.delete_balloon, False),
                         None, ("check", "Save letters", self.save_letters, True)],
            "lettering": [("send", "Calibration sheet…", self.calibration, True), None,
                          ("star", "Favourites only", self.favourites_only, False), ("search", "Rescan fonts", self.rescan_fonts, False)],
        }.get(self.view, [])
        if not cmds:
            bar.addWidget(QLabel("  Nothing to do here yet"))
        for c in cmds:
            if c is None:
                bar.addSeparator()
                continue
            ic, label, slot, primary = c
            act = bar.addAction(icons.icon(ic), label)
            if slot is None:  # "Add balloon": a menu of the five kinds
                menu = QMenu(self)
                for kind, kind_label in KIND_LABELS.items():
                    menu.addAction(kind_label, lambda k=kind: self.add_balloon(k))
                act.setMenu(menu)
                act.triggered.connect(lambda: self.add_balloon("speech"))
                bar.widgetForAction(act).setPopupMode(QToolButton.MenuButtonPopup)
            else:
                act.triggered.connect(slot)
            if primary:
                bar.widgetForAction(act).setProperty("primary", True)
            if label == "Project settings…":
                act.setEnabled(self.project is not None)
            if label == "Favourites only":
                act.setCheckable(True)
                act.setChecked(self.lettering.favorites_only)
                act.triggered.disconnect()
                act.toggled.connect(slot)

    def _update_title(self) -> None:
        name = self.project.name if self.project else "Comic Hub"
        crumbs, status = ["Comics"], ""
        if self.view == "projects":
            crumbs.append("All projects")
            status = f"{len(self.recent())} recent projects" + (f" · open: {self.project.name}" if self.project else "") + \
                     " · double-click a project to open it"
            title = "All projects"
        elif self.view == "pages" and self.project:
            crumbs += [name, self.project.chapter, "Pages"]
            done = sum(e.status == "done" for e in self.project.pages)
            sel = f" · page_{self.selected:02d} selected" if self.selected else ""
            status = f"{len(self.project.pages)} pages · {done} done{sel} · double-click a page to open it in the builder"
            title = f"Pages · {name}"
        elif self.view == "builder" and self.builder.draft:
            d = self.builder.draft
            star = " *" if self.builder.dirty else ""
            crumbs += [name, self.project.chapter, f"page_{d.number:02d}.svg"]
            status = f"{len(d.cells)} panels · gutter {d.gutter:g} mm · " + (
                f"seed {d.layout.get('seed')}" if d.layout.get("kind") == "bsp" else d.layout.get("kind", "custom")) + \
                (" · unsaved changes" if star else "")
            title = f"Page builder · page_{d.number:02d}{star} · {name}"
        elif self.view == "balloons" and self.balloons_view.page:
            n = self.balloons_view.page.number
            star = " *" if self.balloons_view.dirty else ""
            crumbs += [name, self.project.chapter, f"page_{n:02d}.svg", "Balloons"]
            status = self.balloons_view.status_text()
            title = f"Balloons · page_{n:02d}{star} · {name}"
        elif self.view == "lettering" and self.project:
            crumbs += [name, "Lettering"]
            status = self.lettering.status_text()
            title = f"Lettering · {name}"
        else:
            crumbs += [name, self.view.capitalize()]
            title = f"{self.view.capitalize()} · {name}"
        self.crumb.setText("  ▸  ".join(crumbs))
        self.status.setText(status)
        self.setWindowTitle(f"{title} — Comic Hub")

    # ---------- projects ----------
    def new_project(self) -> None:
        dlg = ProjectDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        try:
            p = create_project(v["folder"], v["name"], chapter=v["chapter"], reading=v["reading"], work_scale=v["work_scale"],
                               paper=v["paper"], size=v["size"], folders=v["folders"], blank_pages=v["blank_pages"])
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Couldn't create the project", str(e).capitalize() + ".")
            return
        self.open_project(p.folder, quiet=True)
        self.toast("Project created", f"{p.name}: {len(p.folders)} folders and {len(p.pages)} blank pages in {p.folder}.")

    def open_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open a comic project folder", os.path.expanduser("~"))
        if folder:
            self.open_project(folder)

    def open_project(self, folder: str, quiet: bool = False) -> None:
        if not self._leave_editor():
            return
        try:
            p = load_project(folder)
        except ValueError as e:
            if quiet:
                raise
            QMessageBox.warning(self, "Can't open that folder", str(e).capitalize() + ".")
            return
        self.project = p
        self.selected = p.pages[-1].number if p.pages else None
        self._remember(folder)
        self._build_nav()
        self.back_stack.clear(); self.fwd_stack.clear()
        self.view = "projects"
        self.go("pages", record=False)
        if not quiet:
            self.toast("Project opened", f"{p.name} is now the open project.")

    def project_settings(self) -> None:
        if not self.project:
            return
        dlg = ProjectDialog(self, self.project)
        if not dlg.exec():
            return
        v = dlg.values()
        try:
            self.project = update_settings(self.project, name=v["name"], chapter=v["chapter"], reading=v["reading"],
                                           work_scale=v["work_scale"], paper=v["paper"], size=v["size"], folders=v["folders"])
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Couldn't save the settings", str(e).capitalize() + ".")
            return
        self._build_nav()
        self.go(self.view, record=False)
        self.toast("Settings saved", f"{self.project.name} updated. New pages use the new defaults.")

    # ---------- pages ----------
    def add_page(self) -> None:
        if not self.project:
            return
        dlg = AddPageDialog(self.project, self)
        dlg.wants_batch.connect(self.batch)
        if not dlg.exec():
            return
        page = self.project.new_page(dlg.panels.value(), mode=dlg.mode.currentData(), status=dlg.status.currentData())
        self.selected = page.number
        self.toast("Page added", f"page_{page.number:02d} added to {theme.STATUS_LABELS[dlg.status.currentData()]}.")
        self.go("builder" if dlg.open_builder.isChecked() else "pages", record=self.view != "pages")
        if self.view == "pages":
            self.pages_view.set_project(self.project, self.selected)

    def batch(self) -> None:
        if not self.project:
            return
        dlg = BatchDialog(self.project, self.selected, self)
        if dlg.exec() and dlg.made:
            self.selected = dlg.made[0].number
            n = len(dlg.made)
            self.toast("Pages generated", f"{n} page{'s' if n != 1 else ''} added, page_{dlg.made[0].number:02d} to page_{dlg.made[-1].number:02d}.")
            self.go("pages", record=False)
            self.pages_view.set_project(self.project, self.selected)

    # ---------- builder ----------
    def layout_options(self) -> None:
        if not self.builder.draft:
            return
        dlg = LayoutOptionsDialog(self.builder.draft, self)
        dlg.changed.connect(self.builder.set_draft)
        dlg.changed.connect(lambda _: self._update_title())
        dlg.exec()

    def roll(self) -> None:
        if not self.builder.draft:
            return
        import random
        from cpb_core.build import page_from_bsp
        d = self.builder.draft
        r = d.layout if d.layout.get("kind") == "bsp" else {"panels": max(1, len(d.cells)), "mode": "auto", "snap": True}
        self.builder.set_draft(page_from_bsp(d.number, d.size, r["panels"], mode=r["mode"], seed=random.randrange(10_000, 100_000),
                                             snap=r.get("snap", True), gutter=d.gutter, reading=d.reading, style=d.style))
        self._update_title()

    def save_page(self) -> bool:
        d = self.builder.draft
        if not d or not self.project:
            return False
        from cpb_core.svg import read_page
        path = self.project.page_path(d.number)
        if os.path.exists(path):
            try:
                edited = read_page(path).modified_panels
            except ValueError:
                edited = []
            if edited:
                answer = QMessageBox.question(
                    self, "Panels edited in another app",
                    f"Panel{'s' if len(edited) > 1 else ''} {', '.join(map(str, edited))} of page_{d.number:02d} "
                    "were reshaped outside the hub. Saving redraws them from the layout. Save anyway?")
                if answer != QMessageBox.Yes:
                    return False
        try:
            self.project.save_page(d)
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Couldn't save the page", str(e).capitalize() + ".")
            return False
        self.builder.saved = d
        self.builder.dirty_changed.emit(False)
        self._update_title()
        self.toast("Saved", f"page_{d.number:02d}.svg saved with {len(d.cells)} panels.")
        return True

    # ---------- balloons ----------
    def add_balloon(self, kind: str) -> None:
        if self.balloons_view.page:
            self.balloons_view.add(kind)

    def delete_balloon(self) -> None:
        self.balloons_view.delete_selected()

    def save_letters(self) -> bool:
        v = self.balloons_view
        if not v.page or not self.project:
            return False
        try:
            v.save()
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Couldn't save the balloons", str(e).capitalize() + ".")
            return False
        self._update_title()
        n = len(v.balloons)
        self.toast("Saved", f"page_{v.page.number:02d}.svg saved with {n} balloon{'s' if n != 1 else ''}.")
        return True

    # ---------- lettering ----------
    def calibration(self) -> None:
        if not self.project:
            return
        if not self.lettering.library.entries:
            QMessageBox.information(self, "No fonts found", "The hub couldn't find any fonts to put on the sheet.")
            return
        CalibrationDialog(self.lettering, self).exec()

    def favourites_only(self, on: bool) -> None:
        self.lettering.favorites_only = on
        self.lettering.refresh_table()

    def rescan_fonts(self) -> None:
        self.lettering.library.load(force=True)
        self.lettering.refresh_table()
        lib = self.lettering.library
        self.toast("Fonts rescanned", f"{len(lib.entries)} fonts found" +
                   (f"; {len(lib.errors)} files couldn't be read." if lib.errors else "."))

    def closeEvent(self, event) -> None:
        if not self._leave_editor():
            event.ignore()
            return
        super().closeEvent(event)
