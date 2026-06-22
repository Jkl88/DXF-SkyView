#!/usr/bin/env python3
"""Сборка DXF SkyView в один exe (Windows)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_ONEFILE = ROOT / "DXF-SkyView.spec"
SPEC_ONEDIR = ROOT / "DXF-SkyView-onedir.spec"
DIST_EXE = ROOT / "dist" / "DXF-SkyView.exe"
DIST_ONEDIR_EXE = ROOT / "dist" / "DXF-SkyView" / "DXF-SkyView.exe"
FILE_ICON = ROOT / "DXFfile.ico"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"


def _run(cmd: list[str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    onedir = "--onedir" in sys.argv

    if sys.platform != "win32":
        print("Скрипт рассчитан на сборку Windows exe.")
        print("На других ОС можно запустить PyInstaller вручную:")
        print(f"  pyinstaller {SPEC_ONEFILE.name}")
        return 1

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller не установлен. Выполните:")
        print("  pip install -r requirements-build.txt")
        return 1

    logo = ROOT / "АКОЛЕД.png"
    if not logo.is_file():
        print(f"Предупреждение: не найден логотип {logo.name}")

    print("Иконки...")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_icons.py")], cwd=ROOT)
    if result.returncode != 0:
        print("Ошибка: не удалось создать .ico из PNG.")
        return 1

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)

    spec = SPEC_ONEDIR if onedir else SPEC_ONEFILE
    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(spec),
        ]
    )

    if onedir:
        if not DIST_ONEDIR_EXE.is_file():
            print("Ошибка: exe не создан.")
            return 1
        if FILE_ICON.is_file():
            shutil.copy2(FILE_ICON, DIST_ONEDIR_EXE.parent / FILE_ICON.name)
        target = DIST_ONEDIR_EXE
        print()
        print("Готово (onedir — быстрый запуск).")
        print(f"  Папка: {DIST_ONEDIR_EXE.parent}")
    else:
        if not DIST_EXE.is_file():
            print("Ошибка: exe не создан.")
            return 1
        target = DIST_EXE
        print()
        print("Готово (onefile).")

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"  Файл: {target}")
    print(f"  Размер exe: {size_mb:.1f} МБ")
    print()
    if onedir:
        print("Запускайте dist\\DXF-SkyView\\DXF-SkyView.exe")
    else:
        print("Скопируйте DXF-SkyView.exe на другой компьютер.")
        print("Повторный запуск ускорен кэшем в %LOCALAPPDATA%\\DXF-SkyView\\_runtime")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
