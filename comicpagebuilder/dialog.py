"""
dialog.py — Main dialog, four tabs.

Tab 0: Page Setup      — paper / binding / bleed / resolution / color space
Tab 1: Layout          — preset layout browser
Tab 2: Custom Layout   — BSP randomizer
Tab 3: Project         — batch generation + Setup Masks
"""

import os

from krita import Krita
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel,
    QScrollArea, QFileDialog, QMessageBox, QFrame,
)
from PyQt5.QtCore import Qt

from .page_setup_widget    import PageSetupWidget
from .layout_browser_widget import LayoutBrowserWidget
from .custom_layout_widget  import CustomLayoutWidget
from .project_widget        import ProjectWidget
from .document_builder      import open_document, save_document


class ComicPageBuilderDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comic Page Builder")
        self.setMinimumSize(580, 580)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )
        self._active_layout = None   # whichever layout is "armed" for generation
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._tabs = QTabWidget()

        # Tab 0 — Page Setup
        self._page_setup = PageSetupWidget()
        self._page_setup.spec_changed.connect(self._on_spec_changed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._page_setup)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._tabs.addTab(scroll, "Page Setup")

        # Tab 1 — Layout browser
        self._layout_browser = LayoutBrowserWidget()
        self._layout_browser.layout_selected.connect(self._on_layout_selected)
        self._layout_browser.layout_confirmed.connect(self._on_layout_confirmed)
        self._tabs.addTab(self._layout_browser, "Layout")

        # Tab 2 — Custom / randomizer
        self._custom_layout = CustomLayoutWidget()
        self._custom_layout.layout_ready.connect(self._on_layout_selected)
        self._custom_layout.layouts_changed.connect(self._on_layouts_changed)
        self._tabs.addTab(self._custom_layout, "Custom Layout")

        # Tab 3 — Project
        self._project = ProjectWidget()
        self._project.generate_pages_requested.connect(self._on_batch_generate)
        self._tabs.addTab(self._project, "Project")

        root.addWidget(self._tabs, stretch=1)

        # ---- Status bar ----
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444;")
        root.addWidget(sep)

        self._status_label = QLabel("Choose a layout, then generate.")
        self._status_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px 4px;")
        root.addWidget(self._status_label)

        # ---- Bottom button bar ----
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addStretch()

        self._btn_create = QPushButton("Create in Krita")
        self._btn_create.setMinimumWidth(130)
        self._btn_create.setEnabled(False)
        self._btn_create.setToolTip("Generate and open immediately")
        self._btn_create.clicked.connect(self._on_create)
        bar.addWidget(self._btn_create)

        self._btn_save = QPushButton("Save to Disk\u2026")
        self._btn_save.setMinimumWidth(130)
        self._btn_save.setEnabled(False)
        self._btn_save.setToolTip("Save as .kra then open")
        self._btn_save.clicked.connect(self._on_save)
        bar.addWidget(self._btn_save)

        root.addLayout(bar)

        # Push initial spec into child widgets
        self._on_spec_changed()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_spec_changed(self):
        spec = self._page_setup.get_spec()
        self._custom_layout.set_page_spec(spec)
        self._project.set_page_spec(spec)
        self._refresh_buttons()

    def _on_layouts_changed(self):
        """Called after user saves a custom layout — reload browser and project combos."""
        self._layout_browser.reload_layouts()
        self._project.reload_layouts()

    def _on_layout_selected(self, layout: dict):
        self._active_layout = layout
        n = layout.get("frames", "?")
        self._status_label.setText(
            f"Layout: {layout['name']}  ({n} panel{'s' if n != 1 else ''}) "
            "— ready to generate."
        )
        self._project.set_active_layout(layout)
        self._refresh_buttons()

    def _on_layout_confirmed(self, layout: dict):
        self._on_layout_selected(layout)
        self._on_create()

    def _refresh_buttons(self):
        ready = self._active_layout is not None
        self._btn_create.setEnabled(ready)
        self._btn_save.setEnabled(ready)

    def _on_create(self):
        spec   = self._page_setup.get_spec()
        layout = self._active_layout
        if not layout:
            self._status_label.setText("Please select a layout first.")
            return
        try:
            self._status_label.setText("Generating\u2026")
            self.repaint()
            open_document(spec, layout)
            self._status_label.setText(
                f"\u2713 Created: {layout['name']} at {spec.resolution} dpi"
            )
        except Exception as e:
            QMessageBox.critical(self, "Generation Failed", str(e))
            self._status_label.setText("Generation failed — see error dialog.")

    def _on_save(self):
        spec   = self._page_setup.get_spec()
        layout = self._active_layout
        if not layout:
            self._status_label.setText("Please select a layout first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Comic Page As",
            os.path.expanduser("~"),
            "Krita Document (*.kra)",
        )
        if not path:
            return
        if not path.endswith(".kra"):
            path += ".kra"
        try:
            self._status_label.setText("Saving\u2026")
            self.repaint()
            from .document_builder import build_document, setup_masks
            from krita import Krita
            doc = build_document(spec, layout)
            # Scaffold BEFORE saving so the file on disk has the frame groups.
            try:
                setup_masks(doc)
            except Exception:
                pass
            if not doc.saveAs(path):
                raise RuntimeError(f"Krita could not save to: {path}")
            win = Krita.instance().activeWindow()
            if win:
                win.addView(doc)
            self._status_label.setText(f"\u2713 Saved: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            self._status_label.setText("Save failed — see error dialog.")

    def _on_batch_generate(self, jobs: list):
        """Generate multiple pages sequentially and save each to disk."""
        if not jobs:
            return

        total   = len(jobs)
        failed  = []

        for i, job in enumerate(jobs, start=1):
            self._status_label.setText(
                f"Generating page {i}/{total}: {os.path.basename(job['filename'])}\u2026"
            )
            self.repaint()
            try:
                save_document(job["spec"], job["layout"], job["filename"])
            except Exception as e:
                failed.append(f"Page {i}: {e}")

        if failed:
            QMessageBox.warning(
                self, "Batch Generation — Partial Failure",
                f"{len(failed)} page(s) failed:\n\n" + "\n".join(failed)
            )
            self._status_label.setText(
                f"Batch done with {len(failed)} error(s) — check the dialog."
            )
        else:
            self._status_label.setText(
                f"\u2713 Batch complete — {total} page{'s' if total != 1 else ''} "
                f"saved to {os.path.dirname(jobs[0]['filename'])}"
            )
