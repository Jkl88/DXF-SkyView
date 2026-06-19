#!/usr/bin/env python3
"""Сборка DXF SkyView в один exe (Windows)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "DXF-SkyView.spec"
DIST_EXE = ROOT / "dist" / "DXF-SkyView.exe"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"


def _run(cmd: list[str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    if sys.platform != "win32":
        print("Скрипт рассчитан на сборку Windows exe.")
        print("На других ОС можно запустить PyInstaller вручную:")
        print(f"  pyinstaller {SPEC.name}")
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

    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC),
        ]
    )

    if not DIST_EXE.is_file():
        print("Ошибка: exe не создан.")
        return 1

    size_mb = DIST_EXE.stat().st_size / (1024 * 1024)
    print()
    print("Готово.")
    print(f"  Файл: {DIST_EXE}")
    print(f"  Размер: {size_mb:.1f} МБ")
    print()
    print("Скопируйте DXF-SkyView.exe на другой компьютер.")
    print("Иконка для .dxf вшита в exe (извлекается при ассоциации).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
