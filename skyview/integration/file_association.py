"""Ассоциация .dxf с DXF SkyView (Windows)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from skyview.resources import (
    FILE_ICON_ICO,
    bundled_file_icon_path,
    file_icon_cache_path,
    install_root,
)
from skyview.version import APP_NAME

PROG_ID = "DXF-SkyView.dxf"
FILE_TYPE_NAME = "DXF Drawing (SkyView)"


def _exe_path() -> Path:
    return Path(sys.executable).resolve()


def _app_prog_id() -> str:
    return f"Applications\\{_exe_path().name}"


def _icon_registry_value(icon_path: Path) -> str:
    return f"{icon_path.resolve()},0"


def _bundled_file_icon() -> Path | None:
    return bundled_file_icon_path()


def deploy_file_icon() -> Path:
    """Извлечь вшитую иконку файла (для реестра Windows)."""
    if not getattr(sys, "frozen", False):
        for name in (FILE_ICON_ICO, "DXFfile.png"):
            path = install_root() / name
            if path.is_file():
                return path
        return install_root() / FILE_ICON_ICO

    source = _bundled_file_icon()
    target = file_icon_cache_path()
    if source is None:
        return target

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or source.stat().st_mtime_ns > target.stat().st_mtime_ns:
            shutil.copy2(source, target)
    except OSError:
        if source.is_file():
            return source
    return target if target.is_file() else source


def _set_default_icon_subkey(parent_key, icon_ref: str) -> None:
    """DefaultIcon должен быть подключом, не строковым значением."""
    import winreg

    try:
        winreg.DeleteValue(parent_key, "DefaultIcon")
    except OSError:
        pass
    with winreg.CreateKey(parent_key, "DefaultIcon") as icon_key:
        winreg.SetValue(icon_key, None, winreg.REG_SZ, icon_ref)


def _write_shell_open(parent_key, command: str) -> None:
    import winreg

    with winreg.CreateKey(parent_key, r"shell\open\command") as cmd_key:
        winreg.SetValue(cmd_key, None, winreg.REG_SZ, command)


def _current_dxf_handler() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    for subkey in (
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.dxf\UserChoice",
        r"Software\Classes\.dxf",
    ):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
                if subkey.endswith("UserChoice"):
                    handler, _ = winreg.QueryValueEx(key, "ProgId")
                else:
                    handler, _ = winreg.QueryValueEx(key, None)
                if handler:
                    return str(handler)
        except OSError:
            continue
    return None


def _is_our_dxf_handler() -> bool:
    handler = _current_dxf_handler()
    if not handler:
        return False
    if handler == PROG_ID:
        return True
    app_id = _app_prog_id()
    if handler == app_id:
        return True
    return (
        handler.lower().startswith("applications\\")
        and handler.lower().endswith(_exe_path().name.lower())
    )


def is_dxf_associated() -> bool:
    return _is_our_dxf_handler()


def _notify_shell() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except OSError:
        pass


def _delete_registry_tree(root, subkey: str) -> None:
    import winreg

    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                    _delete_registry_tree(key, child)
                except OSError:
                    break
    except OSError:
        return
    try:
        winreg.DeleteKey(root, subkey)
    except OSError:
        pass


def _write_association_registry(icon_path: Path, exe: Path) -> None:
    import winreg

    icon_ref = _icon_registry_value(icon_path)
    command = f'"{exe}" "%1"'
    app_id = _app_prog_id()

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}") as progid_key:
        winreg.SetValue(progid_key, None, winreg.REG_SZ, FILE_TYPE_NAME)
        _set_default_icon_subkey(progid_key, icon_ref)
        _write_shell_open(progid_key, command)

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, rf"Software\Classes\{app_id}"
    ) as app_key:
        winreg.SetValue(app_key, "FriendlyAppName", winreg.REG_SZ, APP_NAME)
        _set_default_icon_subkey(app_key, icon_ref)
        _write_shell_open(app_key, command)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.dxf") as ext_key:
        winreg.SetValue(ext_key, None, winreg.REG_SZ, PROG_ID)
        _set_default_icon_subkey(ext_key, icon_ref)
        with winreg.CreateKey(ext_key, "OpenWithProgids") as ow_key:
            winreg.SetValue(ow_key, PROG_ID, winreg.REG_SZ, "")
            winreg.SetValue(ow_key, app_id, winreg.REG_SZ, "")


def ensure_dxf_file_icon() -> None:
    """Если .dxf открывается через SkyView — обновить иконку файла в реестре."""
    if sys.platform != "win32" or not _is_our_dxf_handler():
        return
    icon_path = deploy_file_icon()
    if not icon_path.is_file():
        return
    try:
        _write_association_registry(icon_path, _exe_path())
        _notify_shell()
    except OSError:
        pass


def register_dxf_association() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Ассоциация файлов поддерживается только в Windows."

    icon_path = deploy_file_icon()
    if not icon_path.is_file():
        return False, "Не найдена вшитая иконка файла."

    try:
        _write_association_registry(icon_path, _exe_path())
        _notify_shell()
    except OSError as exc:
        return False, f"Не удалось записать в реестр:\n{exc}"

    return True, "Файлы .dxf будут открываться в DXF SkyView."


def unregister_dxf_association() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Ассоциация файлов поддерживается только в Windows."

    if not is_dxf_associated():
        return True, "Ассоциация не была установлена."

    import winreg

    try:
        _delete_registry_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}")
        _delete_registry_tree(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{_app_prog_id()}"
        )
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\.dxf", 0, winreg.KEY_WRITE
        ) as ext_key:
            winreg.DeleteValue(ext_key, "")
        _delete_registry_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\.dxf")
        _notify_shell()
    except OSError as exc:
        return False, f"Не удалось удалить ассоциацию:\n{exc}"

    return True, "Ассоциация .dxf снята."
