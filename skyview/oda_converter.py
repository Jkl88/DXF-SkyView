"""Встроенный ODA File Converter для чтения DWG."""

from __future__ import annotations

import sys
from pathlib import Path

from skyview.resources import app_root, install_root

ODA_SUBDIR = "ODAFileConverter"
ODA_EXE_NAME = "ODAFileConverter.exe"
_configured = False


def bundled_oda_dir() -> Path | None:
    """Каталог с ODAFileConverter.exe (установка или dev-сборка)."""
    install_candidate = install_root() / ODA_SUBDIR
    if (install_candidate / ODA_EXE_NAME).is_file():
        return install_candidate

    if getattr(sys, "frozen", False):
        return None

    dev_candidate = app_root() / "third_party" / "oda" / ODA_SUBDIR
    if (dev_candidate / ODA_EXE_NAME).is_file():
        return dev_candidate
    return None


def bundled_oda_exe() -> Path | None:
    folder = bundled_oda_dir()
    if folder is None:
        return None
    return folder / ODA_EXE_NAME


def is_available() -> bool:
    if sys.platform != "win32":
        return False
    return bundled_oda_exe() is not None


def configure_odafc() -> bool:
    """Указать ezdxf путь к встроенному ODA File Converter."""
    global _configured
    if _configured:
        return is_available()

    _configured = True
    if sys.platform != "win32":
        return False

    exe = bundled_oda_exe()
    if exe is None:
        return False

    import ezdxf

    ezdxf.options.set("odafc-addon", "win_exec_path", f'"{exe}"')
    return True


def ensure_odafc() -> None:
    """Настроить ODA; при отсутствии — понятная ошибка."""
    from ezdxf.addons import odafc

    configure_odafc()
    if odafc.is_installed():
        return

    default = Path(r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe")
    if default.is_file():
        import ezdxf

        ezdxf.options.set("odafc-addon", "win_exec_path", f'"{default}"')
        if odafc.is_installed():
            return

    raise RuntimeError(
        "Для открытия DWG нужен ODA File Converter.\n"
        "Переустановите DXF SkyView или установите ODA вручную:\n"
        "https://www.opendesign.com/guestfiles/oda_file_converter"
    )
