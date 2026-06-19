"""Интеграция с DXF Rectangle Creator (Windows)."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

REG_KEY = r"Software\Jkl88\DXF Rectangle Creator"


def _read_registry() -> dict[str, str] | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            import_formats, _ = winreg.QueryValueEx(key, "ImportFormats")
    except OSError:
        return None

    if not isinstance(install_path, str) or not isinstance(import_formats, str):
        return None
    if not os.path.isfile(install_path):
        return None
    if "dxf" not in import_formats.lower():
        return None

    info = {
        "install_path": install_path,
        "import_formats": import_formats,
    }
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
            version, _ = winreg.QueryValueEx(key, "Version")
            if isinstance(version, str):
                info["version"] = version
    except OSError:
        pass
    return info


def get_installation_info() -> dict[str, Any] | None:
    return _read_registry()


def is_rectangle_creator_available() -> bool:
    return get_installation_info() is not None


def _launch_with_import(exe_path: str, dxf_path: str) -> None:
    subprocess.Popen(
        [exe_path, "--import", os.path.abspath(dxf_path)],
        close_fds=True,
    )


def import_dxf(dxf_path: str) -> tuple[bool, str]:
    """Открыть DXF в DXF Rectangle Creator."""
    path = os.path.abspath(dxf_path)
    if not os.path.isfile(path):
        return False, "Файл не найден."

    info = get_installation_info()
    if info is None:
        return (
            False,
            "DXF Rectangle Creator не установлен.\n"
            "Установите программу и запустите её хотя бы один раз.",
        )

    try:
        # Запуск exe с --import: редактор сам перешлёт файл в уже открытое окно.
        _launch_with_import(info["install_path"], path)
        return True, ""
    except OSError as exc:
        return False, f"Не удалось открыть файл в редакторе:\n{exc}"
