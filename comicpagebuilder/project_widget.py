"""
project_widget.py — Tab 3: Project

Batch generation + Setup Masks with duplicate detection.
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QPushButton, QLabel, QSpinBox,
    QComboBox, QScrollArea, QFrame, QFileDialog,
    QMessageBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal

from .layout_browser_widget import load_all_layouts

MAX_PAGES = 20


class ProjectWidget(QWidget):
    generate_pages_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page_spec     = None
        self._all_layouts   = load_all_layouts()
        self._layout_names  = [l["name"] for l in self._all_layouts]
        self._output_folder = os.path.expanduser("~")
        self._page_rows     = []
        self._build_ui()

    def set_page_spec(self, spec):
        self._page_spec = spec

    def set_active_layout(self, layout: dict):
        if layout and layout.get("name") in self._layout_names:
            idx = self._layout_names.index(layout["name"])
            self._same_combo.setCurrentIndex(idx)

    def reload_layouts(self):
        self._all_layouts  = load_all_layouts()
        self._layout_names = [l["name"] for l in self._all_layouts]
        # Refresh per-page combos and same-combo
        self._rebuild_page_list(self._page_count_spin.value())
        self._repopulate_same_combo()

    def _repopulate_same_combo(self):
        self._same_combo.blockSignals(True)
        self._same_combo.clear()
        for name in self._layout_names:
            self._same_combo.addItem(name)
        self._same_combo.blockSignals(False)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Output folder
        folder_group  = QGroupBox("Output Folder")
        folder_layout = QVBoxLayout(folder_group)

        folder_row = QHBoxLayout()
        self._folder_label = QLabel(self._output_folder)
        self._folder_label.setStyleSheet("color:#aaa; font-size:10px;")
        self._folder_label.setWordWrap(True)
        folder_row.addWidget(self._folder_label, stretch=1)
        browse_btn = QPushButton("Browse\u2026")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(browse_btn)
        folder_layout.addLayout(folder_row)

        scaffold_btn = QPushButton("\U0001f4c1  Initialize Project Folders")
        scaffold_btn.setFixedHeight(26)
        scaffold_btn.setToolTip(
            "Creates: Pages / Characters / Comic Script / "
            "Environment / Reference Images\n"
            "Output folder will switch to the Pages subfolder automatically."
        )
        scaffold_btn.setStyleSheet(
            "QPushButton { font-size:10px; background:#2b2b2b;"
            " border:1px solid #555; border-radius:3px; }"
            "QPushButton:hover { background:#333; }"
        )
        scaffold_btn.clicked.connect(self._on_scaffold_folders)
        folder_layout.addWidget(scaffold_btn)
        root.addWidget(folder_group)

        # Batch settings
        batch_group = QGroupBox("Batch Generation")
        batch_form  = QFormLayout(batch_group)
        batch_form.setSpacing(8)

        self._page_count_spin = QSpinBox()
        self._page_count_spin.setRange(1, MAX_PAGES)
        self._page_count_spin.setValue(8)
        self._page_count_spin.setToolTip(
            f"Maximum {MAX_PAGES} pages per batch.\n"
            "Generating large batches can use significant memory.\n"
            "Run multiple batches for longer comics."
        )
        self._page_count_spin.valueChanged.connect(self._rebuild_page_list)
        batch_form.addRow(f"Pages (max {MAX_PAGES}):", self._page_count_spin)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Same layout for all pages",  "same")
        self._mode_combo.addItem("Random Auto  (BSP balanced)", "random_auto")
        self._mode_combo.addItem("Random Pure  (BSP chaotic)",  "random_pure")
        self._mode_combo.addItem("Custom per page",             "custom")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        batch_form.addRow("Layout mode:", self._mode_combo)

        self._same_combo = QComboBox()
        for name in self._layout_names:
            self._same_combo.addItem(name)
        batch_form.addRow("Layout:", self._same_combo)
        self._same_label = batch_form.labelForField(self._same_combo)

        root.addWidget(batch_group)

        # Per-page list
        self._pages_group = QGroupBox("Per-Page Layout Assignment")
        pages_root = QVBoxLayout(self._pages_group)
        self._pages_scroll = QScrollArea()
        self._pages_scroll.setWidgetResizable(True)
        self._pages_scroll.setFrameShape(QFrame.NoFrame)
        self._pages_scroll.setMinimumHeight(180)
        self._pages_container = QWidget()
        self._pages_layout = QVBoxLayout(self._pages_container)
        self._pages_layout.setContentsMargins(4, 4, 4, 4)
        self._pages_layout.setSpacing(6)
        self._pages_scroll.setWidget(self._pages_container)
        pages_root.addWidget(self._pages_scroll)
        root.addWidget(self._pages_group)
        self._pages_group.setVisible(False)

        # Generate button
        self._gen_btn = QPushButton("\u2699   Generate All Pages")
        self._gen_btn.setMinimumHeight(34)
        self._gen_btn.setStyleSheet(
            "QPushButton { font-size:13px; background:#2a3a2a;"
            " border:1px solid #55aa55; border-radius:4px; }"
            "QPushButton:hover { background:#3a4a3a; }"
        )
        self._gen_btn.clicked.connect(self._on_generate)
        root.addWidget(self._gen_btn)

        # Setup Masks
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#444;")
        root.addWidget(sep)

        masks_group  = QGroupBox("Setup Drawing Layers")
        masks_layout = QVBoxLayout(masks_group)

        masks_hint = QLabel(
            "Drawing layers are created automatically when you generate a page.\n\n"
            "Use these buttons to regenerate them — for example after editing "
            "your layout with Krita's panel tool, or if you accidentally deleted a frame group."
        )
        masks_hint.setWordWrap(True)
        masks_hint.setStyleSheet("color:#888; font-size:10px;")
        masks_layout.addWidget(masks_hint)

        btn_row = QHBoxLayout()
        self._mask_current_btn = QPushButton("\u21ba  Regenerate — Current Document")
        self._mask_current_btn.setMinimumHeight(30)
        self._mask_current_btn.setToolTip("Rebuild frame groups in the active document")
        self._mask_current_btn.clicked.connect(lambda: self._on_setup_masks(all_docs=False))
        btn_row.addWidget(self._mask_current_btn)

        self._mask_all_btn = QPushButton("\u21ba\u21ba Regenerate — All Open Documents")
        self._mask_all_btn.setMinimumHeight(30)
        self._mask_all_btn.setToolTip("Rebuild frame groups in every open comic document")
        self._mask_all_btn.clicked.connect(lambda: self._on_setup_masks(all_docs=True))
        btn_row.addWidget(self._mask_all_btn)

        masks_layout.addLayout(btn_row)
        root.addWidget(masks_group)
        root.addStretch()

        self._rebuild_page_list(self._page_count_spin.value())
        self._on_mode_changed(0)

    def _rebuild_page_list(self, n: int):
        for i in reversed(range(self._pages_layout.count())):
            w = self._pages_layout.itemAt(i).widget()
            if w: w.setParent(None)
        self._page_rows.clear()

        for i in range(n):
            row = QHBoxLayout()
            lbl = QLabel(f"Page {i+1:02d}:")
            lbl.setFixedWidth(64)
            lbl.setStyleSheet("color:#bbb; font-size:11px;")
            combo = QComboBox()
            combo.setMinimumHeight(26)
            combo.addItem("\U0001f3b2 Random Auto",  "__random_auto__")
            combo.addItem("\U0001f3b2 Random Pure",  "__random_pure__")
            for name in self._layout_names:
                combo.addItem(name, name)
            combo.setCurrentIndex(0)
            row.addWidget(lbl)
            row.addWidget(combo, stretch=1)
            wrapper = QWidget()
            wrapper.setMinimumHeight(32)
            wrapper.setLayout(row)
            self._pages_layout.addWidget(wrapper)
            self._page_rows.append(combo)

    def _on_mode_changed(self, _=None):
        mode = self._mode_combo.currentData()
        same = mode == "same"
        self._same_combo.setVisible(same)
        if self._same_label: self._same_label.setVisible(same)
        self._pages_group.setVisible(mode == "custom")

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self._output_folder)
        if folder:
            self._output_folder = folder
            self._folder_label.setText(folder)

    def _on_scaffold_folders(self):
        subfolders = ["Pages", "Characters", "Comic Script", "Environment", "Reference Images"]
        try:
            for f in subfolders:
                os.makedirs(os.path.join(self._output_folder, f), exist_ok=True)
            # Redirect output into the Pages subfolder
            pages_dir = os.path.join(self._output_folder, "Pages")
            self._output_folder = pages_dir
            self._folder_label.setText(pages_dir)
            QMessageBox.information(self, "Project Initialized",
                "Folders created:\n" +
                "\n".join(f"  • {f}" for f in subfolders) +
                f"\n\nOutput will now go to:\n{pages_dir}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Scaffold Failed", f"Could not create folders:\n{e}")

    def _on_generate(self):
        if self._page_spec is None:
            QMessageBox.warning(self, "No Page Setup", "Configure your page in the Page Setup tab first.")
            return
        mode  = self._mode_combo.currentData()
        n     = self._page_count_spin.value()

        # Scan output folder for existing page_XX.kra files so we never overwrite
        start_index = self._next_page_index(self._output_folder)

        jobs = []
        for i in range(n):
            layout = self._resolve_layout(i, mode)
            if layout is None:
                QMessageBox.critical(self, "Layout Error", f"Could not resolve layout for page {i+1}.")
                return
            page_num = start_index + i
            jobs.append({
                "spec":     self._page_spec,
                "layout":   layout,
                "filename": os.path.join(self._output_folder, f"page_{page_num:02d}.kra"),
            })
        self.generate_pages_requested.emit(jobs)

    @staticmethod
    def _next_page_index(folder: str) -> int:
        """
        Scan folder for page_XX.kra files and return the next available index.
        E.g. if page_01.kra and page_02.kra exist, returns 3.
        Returns 1 if folder is empty or doesn't exist.
        """
        import re
        if not os.path.isdir(folder):
            return 1
        highest = 0
        pattern = re.compile(r'^page_(\d+)\.kra$', re.IGNORECASE)
        for fname in os.listdir(folder):
            m = pattern.match(fname)
            if m:
                highest = max(highest, int(m.group(1)))
        return highest + 1

    def _resolve_layout(self, i: int, mode: str):
        from .layout_generator import generate_layout, make_layout_dict
        s   = self._page_spec
        bw  = s.effective_binding_w() if s else 210.0
        bh  = s.effective_binding_h() if s else 297.0
        g   = s.line_strength         if s else 0.5
        if mode == "same":
            name = self._same_combo.currentText()
            m = [l for l in self._all_layouts if l["name"] == name]
            return m[0] if m else None
        elif mode in ("random_auto", "random_pure"):
            cut = "auto" if mode == "random_auto" else "random"
            return make_layout_dict(generate_layout(4, bw, bh, gutter_mm=3.0, cut_mode=cut), f"Random p{i+1}")
        elif mode == "custom":
            if i >= len(self._page_rows): return None
            data = self._page_rows[i].currentData()
            if data == "__random_auto__":
                return make_layout_dict(generate_layout(4, bw, bh, gutter_mm=3.0, cut_mode="auto"), f"Random p{i+1}")
            elif data == "__random_pure__":
                return make_layout_dict(generate_layout(4, bw, bh, gutter_mm=3.0, cut_mode="random"), f"Random p{i+1}")
            else:
                m = [l for l in self._all_layouts if l["name"] == data]
                return m[0] if m else None
        return None

    def _on_setup_masks(self, all_docs: bool):
        from .document_builder import setup_masks, check_has_masks
        try:
            from krita import Krita
            app = Krita.instance()
            if all_docs:
                docs = [d for d in app.documents() if d]
            else:
                win = app.activeWindow()
                if not win or not win.activeView():
                    QMessageBox.warning(self, "No Document", "No active document found.")
                    return
                docs = [win.activeView().document()]

            # Partition: comic (has Panels), already masked, non-comic (skip silently)
            comic_docs  = []
            masked_docs = []
            skipped     = 0
            for d in docs:
                root       = d.rootNode()
                # Current pages build Panels as a group of Panel N layers;
                # older pages used one flat vector layer. Accept both.
                has_panels = any(
                    n.name() == "Panels" and n.type() in ("grouplayer", "vectorlayer")
                    for n in root.childNodes()
                )
                if not has_panels:
                    skipped += 1
                    continue
                if check_has_masks(d):
                    masked_docs.append(d)
                else:
                    comic_docs.append(d)

            if not comic_docs and not masked_docs:
                QMessageBox.information(
                    self, "Nothing Found",
                    "No open documents have a 'Panels' layer.\n"
                    + (f"{skipped} non-comic document{'s were' if skipped != 1 else ' was'} skipped."
                       if skipped else "")
                )
                return

            # Handle already-masked docs
            if masked_docs:
                names = "\n".join(
                    os.path.basename(d.fileName()) or "Unsaved document"
                    for d in masked_docs
                )
                dlg = QMessageBox(self)
                dlg.setWindowTitle("Masks Already Applied")
                dlg.setText(
                    f"The following document{'s' if len(masked_docs) > 1 else ''} already "
                    f"{'have' if len(masked_docs) > 1 else 'has'} frame groups:\n\n{names}\n\n"
                    "What would you like to do?"
                )
                btn_reapply = dlg.addButton("Reapply to all",     QMessageBox.YesRole)
                btn_skip    = dlg.addButton("Skip already masked", QMessageBox.NoRole)
                btn_cancel  = dlg.addButton("Cancel",             QMessageBox.RejectRole)
                dlg.setDefaultButton(btn_skip)
                dlg.exec_()

                clicked = dlg.clickedButton()
                if clicked == btn_cancel:
                    return
                if clicked == btn_reapply:
                    comic_docs = comic_docs + masked_docs
                # btn_skip → comic_docs stays as-is

            if not comic_docs:
                QMessageBox.information(self, "Nothing to Do",
                    "All eligible documents already have masks. No changes made.")
                return

            total  = 0
            errors = []
            for doc in comic_docs:
                try:
                    n = setup_masks(doc)
                    if n > 0:
                        total += n
                except Exception as e:
                    errors.append(
                        f"{os.path.basename(doc.fileName()) or 'Unsaved'}: {e}"
                    )

            msg = f"Setup complete — {total} frame group{'s' if total != 1 else ''} created."
            if skipped:
                msg += f"\n{skipped} non-comic document{'s' if skipped != 1 else ''} skipped."
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors)
                QMessageBox.warning(self, "Done with Errors", msg)
            else:
                QMessageBox.information(self, "Done", msg)

        except Exception as e:
            QMessageBox.critical(self, "Setup Masks Failed", str(e))
