"""
The Script screen (M7): link the comic script, say who's talking, and make
each page's balloons from it.

The reader in cpb_core.script finds pages, panels and labelled lines in most
script layouts. What it can't know is whether "Background:" is a character,
so every label is listed under "Who's talking?" with a first guess ticked;
unticking one turns its lines back into stage notes. The choice is saved in
project.json, so a script you read again keeps it.

The script is copied into the project's script/ folder, so the project
holds everything it needs. If the original changes (you kept writing), it's
copied again the next time the screen opens.
"""

from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from cpb_core.project import Project
from cpb_core.script import SCRIPT_TYPES, Script, apply_script, clean_pdf_text, read_script, script_text

from .balloons_view import default_font_for, fitted

KIND_NAMES = {"speech": "Speech", "caption": "Caption", "thought": "Thought", "shout": "Shout",
              "whisper": "Whisper", "floating": "No balloon", "sfx": "SFX (yours to letter)"}
FILTER = "Scripts (" + " ".join("*" + e for e in SCRIPT_TYPES) + ");;All files (*)"


def read_script_file(path: str) -> Script:
    """Any supported script file as a Script. PDFs are read with pypdfium2."""
    if path.lower().endswith(".pdf"):
        from . import pdf_art
        if not pdf_art.available():
            raise ValueError(pdf_art.INSTALL_HINT)
        return read_script(clean_pdf_text(pdf_art.pdf_text(path)))
    return read_script(script_text(path))


class ScriptView(QWidget):
    applied = Signal(object)        # a ScriptReport, after balloons were made
    status_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.script: Script | None = None
        self.path: str | None = None    # the project's copy of the script
        self._filling = False

        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Script", "Becomes"])
        self.tree.setColumnWidth(0, 560); self.tree.setAlternatingRowColors(True)
        self.tree.setFrameShape(QFrame.NoFrame)
        lay.addWidget(self.tree, 1)

        side = QScrollArea(); side.setWidgetResizable(True); side.setFrameShape(QFrame.NoFrame); side.setFixedWidth(300)
        props = QWidget(); props.setObjectName("DetailsPane"); props.setAttribute(Qt.WA_StyledBackground, True)
        pl = QVBoxLayout(props); pl.setContentsMargins(12, 8, 12, 12)
        side.setWidget(props)
        lay.addWidget(side)

        box = QGroupBox("Script"); bl = QVBoxLayout(box)
        self.file_label = QLabel("No script linked yet."); self.file_label.setObjectName("Hint"); self.file_label.setWordWrap(True)
        row = QHBoxLayout()
        self.open_btn = QPushButton("Open script…"); self.reload_btn = QPushButton("Read again")
        self.reload_btn.setToolTip("Read the script again, after you've changed it")
        row.addWidget(self.open_btn); row.addWidget(self.reload_btn); row.addStretch()
        bl.addWidget(self.file_label); bl.addLayout(row)
        types = QLabel("Text, Markdown, Word, LibreOffice or PDF. From Google Docs: File ▸ Download ▸ .txt or .docx.")
        types.setObjectName("Hint"); types.setWordWrap(True); bl.addWidget(types)
        pl.addWidget(box)

        who = QGroupBox("Who's talking?"); wl = QVBoxLayout(who)
        hint = QLabel("Untick stage notes that look like names (Background:, Close-up:). Their lines won't become balloons.")
        hint.setObjectName("Hint"); hint.setWordWrap(True)
        self.speakers = QListWidget(); self.speakers.setMinimumHeight(180)
        wl.addWidget(hint); wl.addWidget(self.speakers)
        pl.addWidget(who)

        make = QGroupBox("Make balloons"); mf = QFormLayout(make)
        self.first_page = QSpinBox(); self.first_page.setRange(1, 999); self.first_page.setPrefix("page ")
        self.first_page.setToolTip("Which project page the script's page 1 goes on")
        self.existing = QComboBox()
        self.existing.addItem("Leave them alone", "skip"); self.existing.addItem("Add the new ones", "add")
        self.make_btn = QPushButton("Make balloons"); self.make_btn.setProperty("primary", True)
        self.result = QLabel(); self.result.setObjectName("Hint"); self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mf.addRow("Script page 1 is:", self.first_page)
        mf.addRow("Pages with balloons:", self.existing)
        mf.addRow(self.make_btn); mf.addRow(self.result)
        pl.addWidget(make)
        pl.addStretch()

        self.open_btn.clicked.connect(self.choose)
        self.reload_btn.clicked.connect(self.reload)
        self.make_btn.clicked.connect(self.make)
        self.speakers.itemChanged.connect(self._speaker_toggled)
        self.first_page.valueChanged.connect(self._first_page_changed)
        self._show()

    # ---------- the linked script ----------
    def set_project(self, project: Project | None) -> None:
        self.project, self.script, self.path = project, None, None
        self.result.clear()
        link = project.script if project else {}
        if link.get("file"):
            copy = os.path.join(project.folder, *link["file"].split("/"))
            source = link.get("source", "")
            try:
                # You kept writing: the original is newer than the project's copy.
                if source and os.path.exists(source) and (not os.path.exists(copy) or
                                                          os.path.getmtime(source) > os.path.getmtime(copy) + 1):
                    shutil.copyfile(source, copy)
                    self.result.setText(f"Read {os.path.basename(source)} again: it changed since last time.")
                if os.path.exists(copy):
                    self.path = copy
                    self.script = read_script_file(copy)
            except (ValueError, OSError) as e:
                self.result.setText(f"Couldn't read the script: {e}")
        self._show()

    def choose(self) -> None:
        if not self.project:
            return
        start = os.path.dirname(self.project.script.get("source", "")) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Open a comic script", start, FILTER)
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> bool:
        """Read a script, copy it into the project and link it. False (with the reason shown) if it can't."""
        try:
            script = read_script_file(path)
        except (ValueError, OSError) as e:
            self.result.setText(f"Couldn't read {os.path.basename(path)}: {e}")
            return False
        if not script.pages:
            self.result.setText(f"No pages found in {os.path.basename(path)}. The reader looks for headings "
                                "like \"PAGE 1\" or \"Page 1:\"; is that how it's written?")
            return False
        folder = os.path.join(self.project.folder, "script")
        os.makedirs(folder, exist_ok=True)
        copy = os.path.join(folder, os.path.basename(path))
        if os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(copy)):
            shutil.copyfile(path, copy)
        old = self.project.script
        same = old.get("file") == "script/" + os.path.basename(path)
        self.project.script = {"file": "script/" + os.path.basename(path), "source": os.path.abspath(path),
                               "first_page": old.get("first_page", 1) if same else 1,
                               "not_speakers": old.get("not_speakers", []) if same else
                               [k for k in script.speakers() if not script.likely_speaker(k)]}
        self.project.save()
        self.script, self.path = script, copy
        self.result.setText("")
        self._show()
        return True

    def reload(self) -> None:
        source = self.project.script.get("source") if self.project else None
        if source and os.path.exists(source):
            self.load_file(source)
        elif self.project:
            self.set_project(self.project)

    # ---------- the checklist ----------
    def not_speakers(self) -> set[str]:
        if not self.project:
            return set()
        if "not_speakers" in self.project.script:
            return set(self.project.script["not_speakers"])
        return {k for k in self.script.speakers() if not self.script.likely_speaker(k)} if self.script else set()

    def _speaker_toggled(self, item: QListWidgetItem) -> None:
        if self._filling or not self.project:
            return
        off = self.not_speakers()
        key = item.data(Qt.UserRole)
        (off.add if item.checkState() != Qt.Checked else off.discard)(key)
        self.project.script["not_speakers"] = sorted(off)
        self.project.save()
        self._fill_tree()

    def _first_page_changed(self, value: int) -> None:
        if self._filling or not self.project or not self.project.script:
            return
        self.project.script["first_page"] = value
        self.project.save()
        self._fill_tree()

    # ---------- showing it ----------
    def _show(self) -> None:
        self._filling = True
        has = self.script is not None
        for w in (self.reload_btn, self.make_btn, self.speakers, self.first_page, self.existing):
            w.setEnabled(has)
        self.open_btn.setEnabled(self.project is not None)
        if has:
            pages = self.script.pages
            lines = sum(len(p.lines()) for p in pages)
            self.file_label.setText(f"{os.path.basename(self.path)}\n{len(pages)} page{'s' if len(pages) != 1 else ''}, "
                                    f"{lines} line{'s' if lines != 1 else ''} of lettering")
            self.first_page.setValue(int(self.project.script.get("first_page", 1)))
        else:
            self.file_label.setText("No script linked yet.")
        self.speakers.clear()
        if has:
            off = self.not_speakers()
            names = self._display_names()
            for key, count in self.script.speakers().items():
                item = QListWidgetItem(f"{names.get(key, key)}  ·  {count} line{'s' if count != 1 else ''}")
                item.setData(Qt.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked if key in off else Qt.Checked)
                self.speakers.addItem(item)
        self._filling = False
        self._fill_tree()
        self.status_changed.emit()

    def _display_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for page in self.script.pages:
            for line in page.lines():
                if line.label and line.label not in names:
                    names[line.label] = line.speaker or line.label.title()
        return names

    def _fill_tree(self) -> None:
        self.tree.clear()
        if not self.script:
            empty = QTreeWidgetItem(["Open a script to see its pages, panels and lines here."])
            empty.setForeground(0, QBrush(QColor("#7a6a72")))
            self.tree.addTopLevelItem(empty)
            return
        off = self.not_speakers()
        grey = QBrush(QColor("#9a8a92"))
        offset = self.first_page.value() - 1
        have = {e.number for e in self.project.pages}
        for page in self.script.pages:
            target = page.number + offset
            title = f"Page {page.number}" + (f" · {page.title}" if page.title else "")
            where = f"→ page_{target:02d}" if target in have else f"no page_{target:02d} in the project yet"
            pi = QTreeWidgetItem([title, where])
            f = pi.font(0); f.setBold(True); pi.setFont(0, f)
            if target not in have:
                pi.setForeground(1, QBrush(QColor("#b0413e")))
            self.tree.addTopLevelItem(pi)
            for panel in page.panels:
                desc = panel.description
                desc = desc if len(desc) <= 90 else desc[:88] + "…"
                ni = QTreeWidgetItem([f"Panel {panel.number}" + (f" · {desc}" if desc else ""), ""])
                ni.setForeground(0, grey)
                ni.setToolTip(0, panel.description)
                pi.addChild(ni)
                for line in panel.lines:
                    text = line.text.replace("\n", " / ")
                    head = " ".join(x for x in (line.speaker, f"({line.note})" if line.note else "") if x)
                    label = f"{head}: {text}" if head else text
                    becomes = "Stage note (unticked)" if line.label in off else KIND_NAMES[line.kind]
                    li = QTreeWidgetItem([label, becomes])
                    li.setToolTip(0, line.text)
                    if line.label in off:
                        li.setForeground(0, grey); li.setForeground(1, grey)
                    ni.addChild(li)
        self.tree.expandAll()

    def status_text(self) -> str:
        if not self.script:
            return "No script linked · Open script… to read one"
        n = sum(1 for p in self.script.pages for ln in p.lines() if ln.kind != "sfx" and ln.label not in self.not_speakers())
        return f"{len(self.script.pages)} script pages · {n} lines will become balloons"

    # ---------- making balloons ----------
    def make(self) -> None:
        if not (self.project and self.script):
            return
        family = self.font().family()
        report = apply_script(self.project, self.script, first_page=self.first_page.value(),
                              not_speakers=frozenset(self.not_speakers()), existing=self.existing.currentData(),
                              font_for=lambda role: default_font_for(self.project, role, family), fit=fitted)
        self.result.setText(summary(report))
        self.applied.emit(report)


def _pages(numbers: list[int]) -> str:
    return ", ".join(f"page_{n:02d}" for n in numbers)


def summary(report) -> str:
    """What happened, in a few plain lines."""
    out = []
    if report.balloons:
        out.append(f"Made {report.balloons} balloon{'s' if report.balloons != 1 else ''} on {_pages(report.pages)}.")
    elif not report.skipped:
        out.append("No balloons made: no page had lines to letter.")
    if report.skipped:
        out.append(f"Left {_pages(report.skipped)} alone: {'it has' if len(report.skipped) == 1 else 'they have'} "
                   "balloons already. Choose \"Add the new ones\" to add to them.")
    if report.missing:
        out.append("No project page yet for script page" + ("s " if len(report.missing) > 1 else " ") +
                   ", ".join(map(str, report.missing)) + ".")
    if report.sfx:
        sfx = "; ".join(f"page_{n:02d}: " + ", ".join(ln.text for ln in lines) for n, lines in sorted(report.sfx.items()))
        out.append(f"Sound effects to letter yourself: {sfx}.")
    out.extend(report.warnings)
    return "\n".join(out)
