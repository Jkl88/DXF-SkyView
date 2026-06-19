"""Загрузка DXF и преобразование в графические элементы."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import ezdxf
from ezdxf import path as ezdxf_path
from ezdxf.entities import DXFEntity, Insert
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainterPath, QPen

from skyview.dxf.bounds import records_dxf_extents
from skyview.dxf.units import read_units


@dataclass
class EntityRecord:
    """Запись о сущности DXF для отображения и выбора."""

    handle: str
    entity_type: str
    layer: str
    color: QColor
    path: QPainterPath
    entity: DXFEntity
    properties: dict[str, Any] = field(default_factory=dict)


def _aci_to_color(aci: int) -> QColor:
    """Индекс цвета AutoCAD → QColor (упрощённая таблица)."""
    table = {
        1: QColor(255, 0, 0),
        2: QColor(255, 255, 0),
        3: QColor(0, 255, 0),
        4: QColor(0, 255, 255),
        5: QColor(0, 0, 255),
        6: QColor(255, 0, 255),
        7: QColor(255, 255, 255),
        8: QColor(128, 128, 128),
        9: QColor(192, 192, 192),
    }
    return table.get(aci, QColor(200, 200, 200))


def _entity_color(entity: DXFEntity, doc) -> QColor:
    aci = entity.dxf.color
    if aci == 256:  # BYLAYER
        layer = doc.layers.get(entity.dxf.layer)
        aci = layer.dxf.color if layer else 7
    elif aci == 0:  # BYBLOCK
        aci = 7
    if aci < 0:
        return QColor(200, 200, 200)
    if aci < 256:
        return _aci_to_color(aci)
    return QColor(200, 200, 200)


def _path_to_qpainter(ez_path: ezdxf_path.Path, flatten: float = 0.05) -> QPainterPath:
    """Конвертация ezdxf Path в QPainterPath с корректными дугами."""
    qp = QPainterPath()
    started = False
    for v in ez_path.flattening(distance=flatten):
        pt = QPointF(v.x, -v.y)  # DXF Y-up → Qt Y-down
        if not started:
            qp.moveTo(pt)
            started = True
        else:
            qp.lineTo(pt)
    return qp


def _collect_entities(msp, doc) -> list[DXFEntity]:
    """Собрать все сущности, разворачивая INSERT (блоки/отверстия)."""
    result: list[DXFEntity] = []
    for entity in msp:
        if entity.dxftype() == "INSERT":
            insert: Insert = entity
            try:
                for virtual in insert.virtual_entities():
                    result.append(virtual)
            except ezdxf.DXFStructureError:
                result.append(entity)
        else:
            result.append(entity)
    return result


def _entity_properties(entity: DXFEntity) -> dict[str, Any]:
    """Извлечь свойства сущности для панели информации."""
    props: dict[str, Any] = {
        "type": entity.dxftype(),
        "layer": entity.dxf.layer,
        "handle": entity.dxf.handle,
    }
    dxftype = entity.dxftype()

    if dxftype == "LINE":
        start = entity.dxf.start
        end = entity.dxf.end
        length = math.hypot(end.x - start.x, end.y - start.y)
        props["length"] = length
        props["start"] = (start.x, start.y)
        props["end"] = (end.x, end.y)
    elif dxftype == "CIRCLE":
        r = entity.dxf.radius
        props["radius"] = r
        props["diameter"] = 2 * r
        props["center"] = (entity.dxf.center.x, entity.dxf.center.y)
    elif dxftype == "ARC":
        r = entity.dxf.radius
        props["radius"] = r
        props["diameter"] = 2 * r
        props["center"] = (entity.dxf.center.x, entity.dxf.center.y)
        props["start_angle"] = entity.dxf.start_angle
        props["end_angle"] = entity.dxf.end_angle
        span = abs(entity.dxf.end_angle - entity.dxf.start_angle)
        props["arc_length"] = math.radians(span) * r
    elif dxftype == "ELLIPSE":
        major = entity.dxf.major_axis.magnitude
        ratio = entity.dxf.ratio
        props["major_axis"] = major
        props["minor_axis"] = major * ratio
        props["center"] = (entity.dxf.center.x, entity.dxf.center.y)
    elif dxftype == "LWPOLYLINE":
        points = list(entity.get_points("xy"))
        props["vertex_count"] = len(points)
        props["closed"] = entity.closed
        length = 0.0
        for i in range(len(points) - 1):
            length += math.hypot(
                points[i + 1][0] - points[i][0],
                points[i + 1][1] - points[i][1],
            )
        if entity.closed and points:
            length += math.hypot(
                points[0][0] - points[-1][0],
                points[0][1] - points[-1][1],
            )
        props["length"] = length
    elif dxftype == "POLYLINE":
        verts = [v.dxf.location for v in entity.vertices]
        length = 0.0
        for i in range(len(verts) - 1):
            length += math.hypot(
                verts[i + 1].x - verts[i].x,
                verts[i + 1].y - verts[i].y,
            )
        props["length"] = length
        props["vertex_count"] = len(verts)
    elif dxftype == "POINT":
        loc = entity.dxf.location
        props["location"] = (loc.x, loc.y)
    elif dxftype == "TEXT":
        props["text"] = entity.dxf.text
        props["height"] = entity.dxf.height
        props["insert"] = (entity.dxf.insert.x, entity.dxf.insert.y)
    elif dxftype == "MTEXT":
        props["text"] = entity.text
        props["char_height"] = entity.dxf.char_height
    elif dxftype == "SPLINE":
        props["degree"] = entity.dxf.degree
        props["control_points"] = len(entity.control_points)

    return props


def _make_record(entity: DXFEntity, doc, flatten: float) -> EntityRecord | None:
    try:
        ez_path = ezdxf_path.make_path(entity)
    except (TypeError, ValueError, ezdxf.DXFTypeError):
        return None

    if ez_path.has_sub_paths and len(ez_path) == 0:
        return None

    qp = _path_to_qpainter(ez_path, flatten)
    if qp.isEmpty():
        return None

    color = _entity_color(entity, doc)
    return EntityRecord(
        handle=entity.dxf.handle,
        entity_type=entity.dxftype(),
        layer=entity.dxf.layer,
        color=color,
        path=qp,
        entity=entity,
        properties=_entity_properties(entity),
    )


@dataclass
class DxfDocument:
    doc: ezdxf.document.Drawing
    records: list[EntityRecord]
    unit_code: int
    unit_name: str
    unit_short: str
    extents: tuple[float, float, float, float] | None = None


def load_dxf(filepath: str, flatten: float = 0.05) -> DxfDocument:
    """Загрузить DXF файл."""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    unit_code, unit_name, unit_short = read_units(doc)

    records: list[EntityRecord] = []
    for entity in _collect_entities(msp, doc):
        rec = _make_record(entity, doc, flatten)
        if rec:
            records.append(rec)

    extents = None
    if records:
        extents = records_dxf_extents(records)

    return DxfDocument(
        doc=doc,
        records=records,
        unit_code=unit_code,
        unit_name=unit_name,
        unit_short=unit_short,
        extents=extents,
    )


def make_pen(color: QColor, width: float = 1.0, cosmetic: bool = True) -> QPen:
    pen = QPen(color, width)
    pen.setCosmetic(cosmetic)
    return pen
