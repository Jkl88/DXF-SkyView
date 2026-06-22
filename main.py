"""Точка входа DXF SkyView."""

from __future__ import annotations

import sys
from pathlib import Path

APPLY_UPDATE_FLAG = "--apply-update"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _handle_apply_update_argv() -> bool:
    if len(sys.argv) < 4 or sys.argv[1] != APPLY_UPDATE_FLAG:
        return False
    from skyview.updater import apply_downloaded_update

    target = Path(sys.argv[2])
    try:
        parent_pid = int(sys.argv[3])
    except ValueError:
        return True
    raise SystemExit(apply_downloaded_update(target, parent_pid))


def _show_splash(app):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QSplashScreen

    from skyview.resources import logo_path

    path = logo_path()
    if not path.is_file():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    scaled = pixmap.scaled(
        360,
        160,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    splash = QSplashScreen(scaled)
    splash.show()
    app.processEvents()
    return splash


def main() -> int:
    if _handle_apply_update_argv():
        return 0

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from skyview.resources import app_icon
    from skyview.settings_store import load_theme_mode
    from skyview.single_instance import (
        paths_from_argv,
        send_paths_to_running_instance,
        start_single_instance_server,
    )
    from skyview.ui.theme import apply_theme
    from skyview.updater import cleanup_stale_new_exe

    cleanup_stale_new_exe()

    pending_paths = paths_from_argv(sys.argv)

    app = QApplication(sys.argv)
    app.setApplicationName("DXF SkyView")
    app.setOrganizationName("SkyView")

    if pending_paths and send_paths_to_running_instance(pending_paths):
        return 0

    splash = _show_splash(app) if _is_frozen() else None

    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    theme_mode = load_theme_mode()
    dark = apply_theme(app, theme_mode)

    from skyview.main_window import MainWindow

    window = MainWindow(dark=dark, theme_mode=theme_mode)

    def _on_files_from_other_instance(paths: list[str]) -> None:
        window.open_paths(paths)
        window.bring_to_front()

    window._single_instance_server = start_single_instance_server(
        _on_files_from_other_instance
    )

    window.show()
    if splash is not None:
        splash.finish(window)

    if pending_paths:
        QTimer.singleShot(0, lambda: window.open_paths(pending_paths))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
