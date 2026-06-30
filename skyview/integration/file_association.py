"""Ассоциация .dxf и .dwg с DXF SkyView (Windows)."""

from __future__ import annotations

import sys
from pathlib import Path

from skyview.resources import (
    DWG_FILE_ICON_ICO,
    FILE_ICON_ICO,
    bundled_dwg_file_icon_path,
    bundled_file_icon_path,
    deploy_dwg_file_icon,
    install_root,
)
from skyview.version import APP_NAME

DXF_PROG_ID = "DXF-SkyView.dxf"
DWG_PROG_ID = "DXF-SkyView.dwg"
DXF_FILE_TYPE_NAME = "DXF Drawing (SkyView)"
DWG_FILE_TYPE_NAME = "DWG Drawing (SkyView)"


def _exe_path() -> Path:
    return Path(sys.executable).resolve()


def _app_prog_id() -> str:
    return f"Applications\\{_exe_path().name}"


def _icon_registry_value(icon_path: Path) -> str:
    return f"{icon_path.resolve()},0"


def deploy_file_icon() -> Path:
    """Путь к иконке .dxf (рядом с exe после установки)."""
    for base in (install_root(),):
        for name in (FILE_ICON_ICO, "DXFfile.png"):
            path = base / name
            if path.is_file():
                return path
    bundled = bundled_file_icon_path()
    if bundled is not None and bundled.is_file():
        return bundled
    return install_root() / FILE_ICON_ICO


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


def _current_extension_handler(ext: str) -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    for subkey in (
        rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\UserChoice",
        rf"Software\Classes\{ext}",
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


def _is_our_extension_handler(ext: str, prog_id: str) -> bool:
    handler = _current_extension_handler(ext)
    if not handler:
        return False
    if handler == prog_id:
        return True
    app_id = _app_prog_id()
    if handler == app_id:
        return True
    return (
        handler.lower().startswith("applications\\")
        and handler.lower().endswith(_exe_path().name.lower())
    )


def is_dxf_associated() -> bool:
    return _is_our_extension_handler(".dxf", DXF_PROG_ID)


def is_dwg_associated() -> bool:
    return _is_our_extension_handler(".dwg", DWG_PROG_ID)


def is_cad_associated() -> bool:
    return is_dxf_associated() and is_dwg_associated()


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


def _write_extension_association(
    ext: str,
    prog_id: str,
    type_name: str,
    icon_path: Path,
    exe: Path,
) -> None:
    import winreg

    icon_ref = _icon_registry_value(icon_path)
    command = f'"{exe}" "%1"'
    app_id = _app_prog_id()

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}") as progid_key:
        winreg.SetValue(progid_key, None, winreg.REG_SZ, type_name)
        _set_default_icon_subkey(progid_key, icon_ref)
        _write_shell_open(progid_key, command)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as ext_key:
        winreg.SetValue(ext_key, None, winreg.REG_SZ, prog_id)
        _set_default_icon_subkey(ext_key, icon_ref)
        with winreg.CreateKey(ext_key, "OpenWithProgids") as ow_key:
            winreg.SetValue(ow_key, prog_id, winreg.REG_SZ, "")
            winreg.SetValue(ow_key, app_id, winreg.REG_SZ, "")


def _unregister_extension(ext: str, prog_id: str) -> None:
    import winreg

    _delete_registry_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}")
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}", 0, winreg.KEY_WRITE
        ) as ext_key:
            winreg.DeleteValue(ext_key, "")
    except OSError:
        pass
    _delete_registry_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}")


def register_dxf_association() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Ассоциация файлов поддерживается только в Windows."

    import winreg

    dxf_icon = deploy_file_icon()
    dwg_icon = deploy_dwg_file_icon()
    if not dxf_icon.is_file():
        return False, "Не найдена иконка для .dxf."
    if not dwg_icon.is_file():
        return False, "Не найдена иконка для .dwg."

    exe = _exe_path()
    try:
        _write_extension_association(".dxf", DXF_PROG_ID, DXF_FILE_TYPE_NAME, dxf_icon, exe)
        _write_extension_association(".dwg", DWG_PROG_ID, DWG_FILE_TYPE_NAME, dwg_icon, exe)

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{_app_prog_id()}"
        ) as app_key:
            winreg.SetValue(app_key, "FriendlyAppName", winreg.REG_SZ, APP_NAME)
            _set_default_icon_subkey(app_key, _icon_registry_value(dxf_icon))
            _write_shell_open(app_key, f'"{exe}" "%1"')

        _notify_shell()
    except OSError as exc:
        return False, f"Не удалось записать в реестр:\n{exc}"

    return True, "Файлы .dxf и .dwg будут открываться в DXF SkyView."


def unregister_dxf_association() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Ассоциация файлов поддерживается только в Windows."

    if not is_dxf_associated() and not is_dwg_associated():
        return True, "Ассоциация не была установлена."

    import winreg

    try:
        _unregister_extension(".dxf", DXF_PROG_ID)
        _unregister_extension(".dwg", DWG_PROG_ID)
        _delete_registry_tree(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{_app_prog_id()}"
        )
        _notify_shell()
    except OSError as exc:
        return False, f"Не удалось удалить ассоциацию:\n{exc}"

    return True, "Ассоциация .dxf и .dwg снята."
