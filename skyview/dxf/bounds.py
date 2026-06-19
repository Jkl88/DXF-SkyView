"""Точные габариты геометрии DXF (без раздувания от обводки и аппроксимации пути)."""

from __future__ import annotations

from ezdxf import bbox
from ezdxf.entities import DXFEntity
from PySide6.QtCore import QRectF


def entities_dxf_extents(entities: list[DXFEntity]) -> tuple[float, float, float, float] | None:
    """Габарит в координатах DXF: (min_x, min_y, max_x, max_y)."""
    if not entities:
        return None
    box = bbox.extents(entities)
    if not box.has_data:
        return None
    mn, mx = box.extmin, box.extmax
    return mn.x, mn.y, mx.x, mx.y


def records_dxf_extents(records) -> tuple[float, float, float, float] | None:
    return entities_dxf_extents([r.entity for r in records])


def dxf_extents_to_scene_rect(
    extents: tuple[float, float, float, float],
) -> QRectF:
    """Преобразовать DXF-габарит в QRectF сцены (Y инвертирован)."""
    min_x, min_y, max_x, max_y = extents
    width = max_x - min_x
    height = max_y - min_y
    return QRectF(min_x, -max_y, width, height)


def records_scene_bounds(records) -> QRectF:
    extents = records_dxf_extents(records)
    if extents is None:
        return QRectF()
    return dxf_extents_to_scene_rect(extents)


def records_size(records) -> tuple[float, float]:
    """Ширина и высота чертежа в единицах DXF."""
    extents = records_dxf_extents(records)
    if extents is None:
        return 0.0, 0.0
    min_x, min_y, max_x, max_y = extents
    return max_x - min_x, max_y - min_y
