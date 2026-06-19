"""Пути к ресурсам приложения (исходники и собранный exe)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon

LOGO_FILENAME = "АКОЛЕД.png"
APP_ICON_PNG = "DXF.png"
APP_ICON_ICO = "DXF.ico"
FILE_ICON_PNG = "DXFfile.png"
FILE_ICON_ICO = "DXFfile.ico"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def resource_path(name: str) -> Path:
    return app_root() / name


def logo_path() -> Path:
    return resource_path(LOGO_FILENAME)


def app_icon_path() -> Path | None:
    install = install_root()
    for base in (install, app_root()):
        for name in (APP_ICON_ICO, APP_ICON_PNG):
            path = base / name
            if path.is_file():
                return path
    return None


def bundled_file_icon_path() -> Path | None:
    for name in (FILE_ICON_ICO, FILE_ICON_PNG):
        path = resource_path(name)
        if path.is_file():
            return path
    return None


def file_icon_cache_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "SkyView" / FILE_ICON_ICO


def file_icon_path() -> Path | None:
    if getattr(sys, "frozen", False):
        cached = file_icon_cache_path()
        if cached.is_file():
            return cached
        return bundled_file_icon_path()

    for name in (FILE_ICON_ICO, FILE_ICON_PNG):
        path = install_root() / name
        if path.is_file():
            return path
    return None


def app_icon() -> QIcon:
    path = app_icon_path()
    if path is None:
        return QIcon()
    icon = QIcon(str(path))
    return icon if not icon.isNull() else QIcon()


def install_root() -> Path:
    """Корень установки: папка проекта или каталог exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return app_root()
