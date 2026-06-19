"""Пути к ресурсам приложения (исходники и собранный exe)."""

from __future__ import annotations

import sys
from pathlib import Path

LOGO_FILENAME = "АКОЛЕД.png"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def resource_path(name: str) -> Path:
    return app_root() / name


def logo_path() -> Path:
    return resource_path(LOGO_FILENAME)


def install_root() -> Path:
    """Корень установки: папка проекта или каталог exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return app_root()
