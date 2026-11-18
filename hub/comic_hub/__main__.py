import sys

from PySide6.QtWidgets import QApplication

from . import theme
from .icons import mascot
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Comic Hub")
    app.setOrganizationName("Antares")
    app.setWindowIcon(mascot(64))
    theme.apply(app)
    window = MainWindow()
    window.show()
    return app.exec()


sys.exit(main())
