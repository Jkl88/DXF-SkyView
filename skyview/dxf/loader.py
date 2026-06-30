"""Загрузка DXF и преобразование в графические элементы."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPen

from pathlib import Path

from skyview.dxf.bounds import entity_scene_bounds, records_dxf_extents
from skyview.dxf.geometry import (
    _spline_max_points,
    _spline_path_from_points,
    entity_to_qpainter_path,
    spline_path_points,
)
from skyview.dxf.segments import collect_line_segments_for_entity, path_to_pick_segments
from skyview.dxf.units import read_units

_ezdxf_mod: Any = None
_ezdxf_path_mod: Any = None


def _import_ezdxf() -> tuple[Any, Any]:
    global _ezdxf_mod, _ezdxf_path_mod
    if _ezdxf_mod is None:
        import ezdxf
        from ezdxf import path as ezdxf_path

        _ezdxf_mod = ezdxf
        _ezdxf_path_mod = ezdxf_path
    return _ezdxf_mod, _ezdxf_path_mod


@dataclass
class EntityRecord:
    """Запись о сущности DXF для отображения и выбора."""

    handle: str
    entity_type: str
    layer: str
    color: QColor
    path: QPainterPath
    entity: Any
    properties: dict[str, Any] | None = field(default=None, repr=False)
    bounds: QRectF = field(default_factory=QRectF)
    pick_segments: list[tuple[QPointF, QPointF]] = field(default_factory=list)
    analytic_pick: bool = False

    def get_properties(self) -> dict[str, Any]:
        if self.properties is None:
            self.properties = _entity_properties(self.entity)
        return self.properties


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


def _entity_color(entity, doc) -> QColor:
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


def _path_to_qpainter(ez_path, flatten: float = 0.05) -> QPainterPath:
    """Конвертация ezdxf Path в QPainterPath (fallback через flatten)."""
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


def _choose_flatten(entity_count: int) -> float:
    if entity_count > 100_000:
        return 1.0
    if entity_count > 50_000:
        return 0.6
    if entity_count > 20_000:
        return 0.35
    if entity_count > 8_000:
        return 0.2
    if entity_count > 3_000:
        return 0.1
    return 0.05


def _collect_entities(msp, doc) -> list[Any]:
    """Собрать все сущности, разворачивая INSERT (блоки/отверстия)."""
    ezdxf, _ = _import_ezdxf()
    from ezdxf.entities import Insert

    result: list[Any] = []
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


def _entity_properties(entity) -> dict[str, Any]:
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


def _make_record(entity, doc, flatten: float, *, spline_max_points: int) -> EntityRecord | None:
    dxftype = entity.dxftype()

    if dxftype == "SPLINE":
        points = spline_path_points(entity, flatten, spline_max_points)
        qp = _spline_path_from_points(points)
        if qp is None or qp.isEmpty():
            return None
        color = _entity_color(entity, doc)
        rec = EntityRecord(
            handle=entity.dxf.handle,
            entity_type=dxftype,
            layer=entity.dxf.layer,
            color=color,
            path=qp,
            entity=entity,
            bounds=entity_scene_bounds(entity) or qp.boundingRect(),
        )
        rec.pick_segments = [
            (points[i], points[i + 1]) for i in range(len(points) - 1)
        ]
        return rec

    qp = entity_to_qpainter_path(
        entity,
        flatten,
        spline_max_points=spline_max_points,
    )
    if qp is None or qp.isEmpty():
        ezdxf, ezdxf_path = _import_ezdxf()
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
    rec = EntityRecord(
        handle=entity.dxf.handle,
        entity_type=dxftype,
        layer=entity.dxf.layer,
        color=color,
        path=qp,
        entity=entity,
        bounds=entity_scene_bounds(entity) or qp.boundingRect(),
    )

    if dxftype in ("LINE", "CIRCLE", "ARC"):
        rec.analytic_pick = True
    if dxftype in ("LINE", "LWPOLYLINE", "POLYLINE"):
        rec.pick_segments = collect_line_segments_for_entity(entity)
    if not rec.pick_segments and not rec.analytic_pick:
        rec.pick_segments = path_to_pick_segments(qp)
    return rec


@dataclass
class DxfDocument:
    doc: Any
    records: list[EntityRecord]
    unit_code: int
    unit_name: str
    unit_short: str
    extents: tuple[float, float, float, float] | None = None


def _read_dwg(filepath: str) -> Any:
    try:
        from ezdxf.addons import odafc
    except ImportError as exc:
        raise RuntimeError("Модуль чтения DWG недоступен.") from exc

    from skyview.oda_converter import ensure_odafc

    try:
        ensure_odafc()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Для открытия DWG установите ODA File Converter:\n"
            "https://www.opendesign.com/guestfiles/oda_file_converter"
        ) from exc

    try:
        return odafc.readfile(filepath)
    except odafc.ODAFCNotInstalledError as exc:
        raise RuntimeError(
            "ODA File Converter не найден. Переустановите DXF SkyView."
        ) from exc
    except odafc.UnsupportedFileFormat as exc:
        raise RuntimeError("Формат DWG не поддерживается.") from exc
    except odafc.ODAFCError as exc:
        raise RuntimeError(f"Не удалось прочитать DWG:\n{exc}") from exc


def _open_cad_document(filepath: str) -> Any:
    ezdxf, _ = _import_ezdxf()
    ext = Path(filepath).suffix.lower()
    if ext == ".dwg":
        return _read_dwg(filepath)
    return ezdxf.readfile(filepath)


def load_cad(filepath: str, flatten: float | None = None) -> DxfDocument:
    """Загрузить DXF или DWG файл."""
    doc = _open_cad_document(filepath)
    msp = doc.modelspace()
    unit_code, unit_name, unit_short = read_units(doc)

    entities = _collect_entities(msp, doc)
    if flatten is None:
        flatten = _choose_flatten(len(entities))

    spline_count = sum(1 for entity in entities if entity.dxftype() == "SPLINE")
    spline_max_points = _spline_max_points(len(entities), spline_count)

    records: list[EntityRecord] = []
    for entity in entities:
        rec = _make_record(
            entity,
            doc,
            flatten,
            spline_max_points=spline_max_points,
        )
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


def load_dxf(filepath: str, flatten: float | None = None) -> DxfDocument:
    """Загрузить DXF файл (совместимость)."""
    return load_cad(filepath, flatten)


def make_pen(color: QColor, width: float = 1.0, cosmetic: bool = True) -> QPen:
    pen = QPen(color, width)
    pen.setCosmetic(cosmetic)
    return pen
