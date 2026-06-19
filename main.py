"""Точка входа DXF SkyView."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from skyview.integration.file_association import ensure_dxf_file_icon
from skyview.main_window import MainWindow
from skyview.resources import app_icon
from skyview.settings_store import load_theme_mode
from skyview.ui.theme import apply_theme
from skyview.updater import (
    APPLY_UPDATE_FLAG,
    apply_downloaded_update,
    cleanup_stale_new_exe,
)


def _handle_apply_update_argv() -> bool:
    if len(sys.argv) < 4 or sys.argv[1] != APPLY_UPDATE_FLAG:
        return False
    target = Path(sys.argv[2])
    try:
        parent_pid = int(sys.argv[3])
    except ValueError:
        return True
    raise SystemExit(apply_downloaded_update(target, parent_pid))


def main() -> int:
    if _handle_apply_update_argv():
        return 0

    cleanup_stale_new_exe()

    app = QApplication(sys.argv)
    app.setApplicationName("DXF SkyView")
    app.setOrganizationName("SkyView")

    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    ensure_dxf_file_icon()

    theme_mode = load_theme_mode()
    dark = apply_theme(app, theme_mode)

    window = MainWindow(dark=dark, theme_mode=theme_mode)
    window.show()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        window.load_file(path)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
