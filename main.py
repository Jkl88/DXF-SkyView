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


def _finish_splash_animated(splash, window) -> None:
    from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    duration_ms = 700  # Быстрый zoom + fade, не более 1 секунды.
    start_rect = splash.geometry()
    if not start_rect.isValid():
        splash.finish(window)
        return

    grow = 1.14
    target_w = int(start_rect.width() * grow)
    target_h = int(start_rect.height() * grow)
    center = start_rect.center()
    target_rect = QRect(
        int(center.x() - target_w / 2),
        int(center.y() - target_h / 2),
        target_w,
        target_h,
    )

    opacity_effect = QGraphicsOpacityEffect(splash)
    splash.setGraphicsEffect(opacity_effect)

    geom_anim = QPropertyAnimation(splash, b"geometry", splash)
    geom_anim.setDuration(duration_ms)
    geom_anim.setStartValue(start_rect)
    geom_anim.setEndValue(target_rect)
    geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    fade_anim = QPropertyAnimation(opacity_effect, b"opacity", splash)
    fade_anim.setDuration(duration_ms)
    fade_anim.setStartValue(1.0)
    fade_anim.setEndValue(0.0)
    fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)

    group = QParallelAnimationGroup(splash)
    group.addAnimation(geom_anim)
    group.addAnimation(fade_anim)

    def _finalize() -> None:
        splash.finish(window)
        splash.deleteLater()

    group.finished.connect(_finalize)
    splash._finish_anim_group = group
    group.start()


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
        _finish_splash_animated(splash, window)

    if pending_paths:
        QTimer.singleShot(0, lambda: window.open_paths(pending_paths))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
