"""Import drawn pages: images and PDF pages become pages you can letter (D7)."""

from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QMessageBox, QProgressBar, QPushButton, QSpinBox, QVBoxLayout,
)

from cpb_core.art import IMAGE_EXTENSIONS, art_size, image_info
from cpb_core.model import Page
from cpb_core.project import STATUSES, Project

from . import pdf_art, theme

FILTER = "Drawn pages (*.png *.jpg *.jpeg *.webp *.pdf);;Images (*.png *.jpg *.jpeg *.webp);;PDF (*.pdf)"


class ImportArtDialog(QDialog):
    """Pick images and PDFs; each image and each PDF page becomes one page."""

    def __init__(self, project: Project, parent=None, files: list[str] | None = None):
        super().__init__(parent)
        self.project = project
        self.sources: list[tuple[str, int | None]] = []  # (file, PDF page index or None)
        self.made: list[Page] = []
        self.setWindowTitle("Import drawn pages")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        title = QLabel(f"Add drawn pages to {project.name}"); title.setObjectName("GroupTitle")
        lay.addWidget(title)
        hint = QLabel("Each image, and each page of a PDF, becomes a page at its real size, ready for balloons. "
                      "The art is copied into the page's folder and linked under the letters.")
        hint.setObjectName("Hint"); hint.setWordWrap(True)
        lay.addWidget(hint)

        files_box = QGroupBox("Files"); fl = QVBoxLayout(files_box)
        self.list = QListWidget(); self.list.setMinimumHeight(140)
        fl.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton("Add files…"); add.clicked.connect(self.choose)
        clear = QPushButton("Clear"); clear.clicked.connect(lambda: self.set_files([]))
        row.addWidget(add); row.addWidget(clear); row.addStretch()
        fl.addLayout(row)
        lay.addWidget(files_box)

        opts = QGroupBox("Size"); of = QFormLayout(opts)
        self.bleed = QCheckBox(f"The art includes the bleed (painted {project.size.bleed:g} mm past the trim)")
        self.dpi = QSpinBox(); self.dpi.setRange(72, 2400); self.dpi.setValue(project.size.dpi); self.dpi.setSuffix(" dpi")
        self.status = QComboBox()
        for s in STATUSES:
            self.status.addItem(theme.STATUS_LABELS[s], s)
        self.status.setCurrentIndex(STATUSES.index("letters"))
        of.addRow(self.bleed)
        of.addRow("Resolution:", self.dpi)
        res_hint = QLabel("Used for images that don't store a resolution, and to render PDF pages.")
        res_hint.setObjectName("Hint"); res_hint.setWordWrap(True)
        of.addRow(res_hint)
        of.addRow("Status:", self.status)
        lay.addWidget(opts)

        self.summary = QLabel(); self.summary.setObjectName("Hint"); self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.progress = QProgressBar(); self.progress.hide()
        lay.addWidget(self.progress)
        btns = QHBoxLayout(); btns.addStretch()
        self.ok = QPushButton("Import"); self.ok.setDefault(True); self.ok.clicked.connect(self.run)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(self.ok); btns.addWidget(cancel)
        lay.addLayout(btns)
        self.bleed.toggled.connect(lambda _: self._summarize())
        self.dpi.valueChanged.connect(lambda _: self._summarize())
        self.set_files(files or [])

    def choose(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Import drawn pages", os.path.expanduser("~"), FILTER)
        if files:
            self.set_files(self._files() + files)

    def _files(self) -> list[str]:
        return list(dict.fromkeys(f for f, _ in self.sources))

    def set_files(self, files: list[str]) -> None:
        """Expand the chosen files into one source per page, in the order chosen."""
        self.sources, problems = [], []
        self.list.clear()
        for f in dict.fromkeys(files):
            name = os.path.basename(f)
            if f.lower().endswith(".pdf"):
                if not pdf_art.available():
                    problems.append(f"{name}: {pdf_art.INSTALL_HINT}")
                    continue
                try:
                    n = pdf_art.page_count(f)
                except Exception as e:  # pypdfium2 raises its own error types for damaged PDFs
                    problems.append(f"{name}: can't be read ({e})")
                    continue
                for i in range(n):
                    self.sources.append((f, i))
                    self.list.addItem(f"{name} · PDF page {i + 1}")
            elif f.lower().endswith(IMAGE_EXTENSIONS):
                try:
                    info = image_info(f)
                except (OSError, ValueError) as e:
                    problems.append(f"{name}: {e}")
                    continue
                self.sources.append((f, None))
                res = f"{info.dpi:g} dpi" if info.dpi else "no resolution stored"
                self.list.addItem(f"{name} · {info.width} × {info.height} px · {res}")
            else:
                problems.append(f"{name}: not a PNG, JPEG, WebP or PDF")
        self.problems = problems
        self._summarize()

    def _summarize(self) -> None:
        n = len(self.sources)
        first = self.project.next_number()
        text = (f"{n} page{'s' if n != 1 else ''}: page_{first:02d}" + (f" to page_{first + n - 1:02d}" if n > 1 else "")
                if n else "Add images or PDFs to import.")
        sizes = set()
        for f, idx in self.sources[:20]:
            if idx is None:
                try:
                    s, _r = art_size(image_info(f), dpi=None, fallback_dpi=self.dpi.value(), bleed=self.project.size.bleed,
                                     includes_bleed=self.bleed.isChecked(), safe=self.project.size.safe,
                                     margin=self.project.size.margin)
                    sizes.add(f"{s.trim_w:.1f} × {s.trim_h:.1f} mm")
                except (OSError, ValueError):
                    pass
        if sizes:
            text += " · trim " + ", ".join(sorted(sizes)[:3]) + (" …" if len(sizes) > 3 else "")
        if self.problems:
            text += "\n\nSkipped:\n" + "\n".join(self.problems)
        self.summary.setText(text)
        self.ok.setEnabled(n > 0)

    def run(self) -> None:
        """Import every source. Stops at the first failure and keeps what was already made."""
        self.progress.setRange(0, len(self.sources)); self.progress.setValue(0); self.progress.show()
        self.ok.setEnabled(False)
        self.made = []
        for f, idx in self.sources:
            try:
                if idx is None:
                    page = self.project.add_art_page(f, includes_bleed=self.bleed.isChecked(),
                                                     status=self.status.currentData(),
                                                     dpi=None if image_info(f).dpi else self.dpi.value())
                else:
                    tmp = os.path.join(tempfile.mkdtemp(prefix="cpb-pdf-"), "page.png")
                    pdf_art.render_page(f, idx, self.dpi.value(), tmp)
                    page = self.project.add_art_page(tmp, dpi=self.dpi.value(), includes_bleed=self.bleed.isChecked(),
                                                     status=self.status.currentData(), keep_source=False)
                    os.rmdir(os.path.dirname(tmp))
            except Exception as e:  # a bad file shouldn't lose the pages already imported
                where = os.path.basename(f) + (f", page {idx + 1}" if idx is not None else "")
                QMessageBox.warning(self, "Import stopped", f"{where} couldn't be imported: {e}.\n\n"
                                    f"{len(self.made)} page(s) were imported before it.")
                break
            self.made.append(page)
            self.progress.setValue(len(self.made))
            QApplication.processEvents()
        self.accept()
