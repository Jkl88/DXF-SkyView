#!/usr/bin/env python3
"""Сборка установщика DXF-SkyView.exe (onedir + Inno Setup)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_ONEDIR = ROOT / "DXF-SkyView-onedir.spec"
ISS_FILE = ROOT / "installer" / "DXF-SkyView.iss"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
DIST_APP_DIR = DIST_DIR / "DXF-SkyView"
DIST_APP_EXE = DIST_APP_DIR / "DXF-SkyView.exe"
SETUP_EXE = DIST_DIR / "DXF-SkyView.exe"
FILE_ICON = ROOT / "DXFfile.ico"
DWG_FILE_ICON = ROOT / "DWGfile.ico"
VERSION_FILE = ROOT / "skyview" / "version.py"
ODA_BUNDLE_DIR = ROOT / "third_party" / "oda" / "ODAFileConverter"
ODA_DIST_DIR = DIST_APP_DIR / "ODAFileConverter"
FETCH_ODA_SCRIPT = ROOT / "scripts" / "fetch_oda_converter.py"


def _run(cmd: list[str], **kwargs) -> None:
    print(">", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def read_app_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not match:
        raise RuntimeError(f"Не найден APP_VERSION в {VERSION_FILE}")
    return match.group(1)


def find_iscc() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ensure_oda_bundle() -> None:
    if not FETCH_ODA_SCRIPT.is_file():
        raise RuntimeError(f"Не найден {FETCH_ODA_SCRIPT}")

    print("ODA File Converter...")
    _run([sys.executable, str(FETCH_ODA_SCRIPT)])
    if not (ODA_BUNDLE_DIR / "ODAFileConverter.exe").is_file():
        raise RuntimeError(f"Не найден {ODA_BUNDLE_DIR / 'ODAFileConverter.exe'}")


def copy_oda_to_dist() -> None:
    if ODA_DIST_DIR.exists():
        shutil.rmtree(ODA_DIST_DIR)
    shutil.copytree(
        ODA_BUNDLE_DIR,
        ODA_DIST_DIR,
        ignore=shutil.ignore_patterns("*.msi"),
    )


def build_onedir(clean: bool = True) -> None:
    if clean:
        if DIST_DIR.exists():
            shutil.rmtree(DIST_DIR)
        if BUILD_DIR.exists():
            shutil.rmtree(BUILD_DIR)

    ensure_oda_bundle()

    print("Иконки...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_icons.py")],
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError("Не удалось создать .ico из PNG.")

    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_ONEDIR),
        ]
    )

    if not DIST_APP_EXE.is_file():
        raise RuntimeError(f"Не найден {DIST_APP_EXE}")

    if FILE_ICON.is_file() and not (DIST_APP_DIR / FILE_ICON.name).is_file():
        shutil.copy2(FILE_ICON, DIST_APP_DIR / FILE_ICON.name)
    if DWG_FILE_ICON.is_file() and not (DIST_APP_DIR / DWG_FILE_ICON.name).is_file():
        shutil.copy2(DWG_FILE_ICON, DIST_APP_DIR / DWG_FILE_ICON.name)

    copy_oda_to_dist()


def build_inno_setup(version: str) -> None:
    iscc = find_iscc()
    if iscc is None:
        raise RuntimeError(
            "Inno Setup 6 не найден.\n"
            "Установите с https://jrsoftware.org/isinfo.php\n"
            "После установки перезапустите сборку."
        )

    _run(
        [
            str(iscc),
            f"/DMyAppVersion={version}",
            str(ISS_FILE),
        ],
        cwd=ISS_FILE.parent,
    )

    if not SETUP_EXE.is_file():
        raise RuntimeError(f"Установщик не создан: {SETUP_EXE}")


def main() -> int:
    if sys.platform != "win32":
        print("Установщик собирается только на Windows.")
        return 1

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller не установлен: pip install -r requirements-build.txt")
        return 1

    app_only = "--app-only" in sys.argv

    try:
        version = read_app_version()
        print(f"Версия: {version}")
        build_onedir(clean=not app_only)
        if app_only:
            print()
            print("Готово (папка приложения).")
            print(f"  {DIST_APP_EXE}")
            return 0

        build_inno_setup(version)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Ошибка: {exc}")
        return 1

    size_mb = SETUP_EXE.stat().st_size / (1024 * 1024)
    print()
    print("Готово.")
    print(f"  Установщик: {SETUP_EXE}")
    print(f"  Размер: {size_mb:.1f} МБ")
    print()
    print("Распространяйте DXF-SkyView.exe (установщик).")
    print("Устанавливает в Program Files, ассоциация .dxf и .dwg — при установке.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
