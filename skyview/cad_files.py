"""Общие функции для путей и типов CAD-файлов."""

from __future__ import annotations

import os
from pathlib import Path

CAD_EXTENSIONS = (".dxf", ".dwg")


def is_cad_file(path: str) -> bool:
    return Path(path).suffix.lower() in CAD_EXTENSIONS


def absolute_path(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def compare_path_key(path: str) -> str:
    """Ключ для сравнения путей без учёта регистра (Windows)."""
    return os.path.normcase(absolute_path(path))


def open_file_filter() -> str:
    return "CAD файлы (*.dxf *.dwg);;DXF (*.dxf);;DWG (*.dwg);;Все файлы (*.*)"


def save_file_filter() -> str:
    return "DXF (*.dxf);;Все файлы (*.*)"


def save_path_for_cad(path: str) -> str:
    """Путь для сохранения: DWG сохраняется как DXF с тем же именем."""
    path = absolute_path(path)
    if path.lower().endswith(".dwg"):
        return path[:-4] + ".dxf"
    return path
