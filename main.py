"""Точка входа DXF SkyView."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from skyview.main_window import MainWindow
from skyview.ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DXF SkyView")
    app.setOrganizationName("SkyView")

    dark = apply_theme(app)

    window = MainWindow(dark=dark)
    window.show()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        window.load_file(path)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
