from krita import Extension
from PyQt5.QtWidgets import QAction

from .dialog import ComicPageBuilderDialog


class ComicPageBuilderExtension(Extension):
    """
    Entry point for the Comic Page Builder plugin.

    Krita calls setup() once at startup, then the user can trigger the
    dialog any number of times from Tools > Scripts > Comic Page Builder.
    We keep one dialog instance alive for the session so the user's
    settings are remembered between opens.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._dialog = None  # created lazily on first use

    def setup(self):
        # Nothing to initialise at startup — dialog is lazy.
        pass

    def createActions(self, window):
        action = window.createAction(
            "comic_page_builder",          # unique action ID
            "Comic Page Builder",          # label shown in menu
            "tools/scripts",               # menu location
        )
        action.triggered.connect(self._open_dialog)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _open_dialog(self):
        # Build the dialog once, reuse it afterwards.
        if self._dialog is None:
            self._dialog = ComicPageBuilderDialog()

        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
