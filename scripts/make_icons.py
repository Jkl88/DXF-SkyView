#!/usr/bin/env python3
"""Сгенерировать .ico из PNG для exe и ассоциации файлов."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
PAIRS = (
    ("DXF.png", "DXF.ico"),
    ("DXFfile.png", "DXFfile.ico"),
)


def _png_to_ico(png_path: Path, ico_path: Path) -> None:
    from PIL import Image

    image = Image.open(png_path)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    image.save(ico_path, format="ICO", sizes=ICON_SIZES)


def main() -> int:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Установите Pillow: pip install Pillow")
        return 1

    ok = True
    for png_name, ico_name in PAIRS:
        png_path = ROOT / png_name
        ico_path = ROOT / ico_name
        if not png_path.is_file():
            print(f"Пропуск: не найден {png_name}")
            ok = False
            continue
        _png_to_ico(png_path, ico_path)
        print(f"  {ico_path.name}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
