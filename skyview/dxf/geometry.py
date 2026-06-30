"""Быстрое построение путей и геометрический выбор без аппроксимации."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

from skyview.dxf.segments import nearest_on_segment, to_qt

_SPLINE_MAX_POINTS_DEFAULT = 64
_SPLINE_MAX_POINTS_DENSE = 36


def _subsample_points(points: list[QPointF], max_points: int) -> list[QPointF]:
    if len(points) <= max_points:
        return points
    if max_points < 2:
        return points[:1]
    last = len(points) - 1
    return [points[int(i * last / (max_points - 1))] for i in range(max_points)]


_SPLINE_MAX_POINTS_HD = 128


def simplify_qpainter_path(path: QPainterPath, max_points: int = 32) -> QPainterPath:
    """Упрощённый контур для LOD вне экрана."""
    if path.elementCount() <= max_points + 1:
        return path

    simplified = path.simplified()
    if simplified.elementCount() <= max_points + 1:
        return simplified

    points: list[QPointF] = []
    for i in range(simplified.elementCount()):
        el = simplified.elementAt(i)
        if el.type in (
            QPainterPath.ElementType.MoveToElement,
            QPainterPath.ElementType.LineToElement,
        ):
            points.append(QPointF(el.x, el.y))
    if len(points) < 2:
        return simplified

    reduced = _subsample_points(points, max_points)
    result = _spline_path_from_points(reduced)
    return result if result is not None else simplified


def _spline_max_points(entity_count: int, spline_count: int) -> int:
    if spline_count >= 200 or entity_count >= 1500:
        return _SPLINE_MAX_POINTS_DENSE
    if spline_count >= 80:
        return 48
    return _SPLINE_MAX_POINTS_DEFAULT


def _dxf_y(y: float) -> float:
    return -y


def _line_path(entity) -> QPainterPath:
    start = entity.dxf.start
    end = entity.dxf.end
    path = QPainterPath()
    path.moveTo(start.x, _dxf_y(start.y))
    path.lineTo(end.x, _dxf_y(end.y))
    return path


def _circle_path(entity) -> QPainterPath:
    center = entity.dxf.center
    radius = entity.dxf.radius
    cx, cy = center.x, _dxf_y(center.y)
    path = QPainterPath()
    path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
    return path


def _arc_path(entity) -> QPainterPath:
    """Дуга через cubic Bezier из ezdxf path (без flatten)."""
    from ezdxf import path as ezdxf_path

    ez_path = ezdxf_path.make_path(entity)
    return _path_from_ezdxf_commands(ez_path)


def _path_from_ezdxf_commands(ez_path) -> QPainterPath | None:
    from ezdxf.path import Command

    qp = QPainterPath()
    started = False
    current: QPointF | None = None

    start = getattr(ez_path, "start", None)
    if start is not None:
        current = QPointF(start.x, _dxf_y(start.y))
        qp.moveTo(current)
        started = True

    for item in ez_path:
        if item.type == Command.MOVE_TO:
            current = QPointF(item.end.x, _dxf_y(item.end.y))
            if not started:
                qp.moveTo(current)
                started = True
            else:
                qp.moveTo(current)
        elif item.type == Command.LINE_TO and current is not None:
            current = QPointF(item.end.x, _dxf_y(item.end.y))
            qp.lineTo(current)
        elif item.type == Command.CURVE3_TO and current is not None:
            c1 = QPointF(item.ctrl1.x, _dxf_y(item.ctrl1.y))
            end = QPointF(item.end.x, _dxf_y(item.end.y))
            qp.quadTo(c1, end)
            current = end
        elif item.type == Command.CURVE4_TO and current is not None:
            c1 = QPointF(item.ctrl1.x, _dxf_y(item.ctrl1.y))
            c2 = QPointF(item.ctrl2.x, _dxf_y(item.ctrl2.y))
            end = QPointF(item.end.x, _dxf_y(item.end.y))
            qp.cubicTo(c1, c2, end)
            current = end
        elif item.type == Command.CLOSE_PATH and current is not None:
            qp.closeSubpath()

    if not started:
        return None
    return qp


def _spline_path_from_points(points: list[QPointF]) -> QPainterPath | None:
    if not points:
        return None
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)
    return path


def _spline_path(entity, flatten: float, max_points: int) -> QPainterPath | None:
    return _spline_path_from_points(spline_path_points(entity, flatten, max_points))


def spline_path_points(entity, flatten: float, max_points: int) -> list[QPointF]:
    from ezdxf import path as ezdxf_path

    ez_path = ezdxf_path.make_path(entity)
    verts = [QPointF(v.x, _dxf_y(v.y)) for v in ez_path.flattening(distance=flatten)]
    return _subsample_points(verts, max_points)


def entity_to_qpainter_path(
    entity,
    flatten: float,
    *,
    spline_max_points: int = _SPLINE_MAX_POINTS_DEFAULT,
) -> QPainterPath | None:
    """Построить QPainterPath; для простых типов — без flatten."""
    dxftype = entity.dxftype()
    if dxftype == "LINE":
        return _line_path(entity)
    if dxftype == "CIRCLE":
        return _circle_path(entity)
    if dxftype == "ARC":
        return _arc_path(entity)
    if dxftype == "SPLINE":
        return _spline_path(entity, flatten, spline_max_points)

    from ezdxf import path as ezdxf_path

    try:
        ez_path = ezdxf_path.make_path(entity)
    except (TypeError, ValueError):
        return None

    if ez_path.has_sub_paths and len(ez_path) == 0:
        return None

    fast = _path_from_ezdxf_commands(ez_path)
    if fast is not None and not fast.isEmpty():
        return fast

    qp = QPainterPath()
    started = False
    for vertex in ez_path.flattening(distance=flatten):
        point = QPointF(vertex.x, _dxf_y(vertex.y))
        if not started:
            qp.moveTo(point)
            started = True
        else:
            qp.lineTo(point)
    return qp if started else None


def pick_distance_to_entity(cursor: QPointF, entity) -> float | None:
    """Расстояние от курсора до контура сущности (аналитика для дуг/окружностей)."""
    dxftype = entity.dxftype()
    if dxftype == "LINE":
        start = entity.dxf.start
        end = entity.dxf.end
        return _segment_distance(
            cursor,
            to_qt(start.x, start.y),
            to_qt(end.x, end.y),
        )
    if dxftype == "CIRCLE":
        center = entity.dxf.center
        radius = entity.dxf.radius
        center_qt = to_qt(center.x, center.y)
        dist_center = math.hypot(cursor.x() - center_qt.x(), cursor.y() - center_qt.y())
        return abs(dist_center - radius)
    if dxftype == "ARC":
        return _arc_pick_distance(cursor, entity)
    return None


def _segment_distance(cursor: QPointF, a: QPointF, b: QPointF) -> float:
    foot = nearest_on_segment(cursor, a, b)
    return math.hypot(cursor.x() - foot.x(), cursor.y() - foot.y())


def _arc_pick_distance(cursor: QPointF, entity) -> float | None:
    center = entity.dxf.center
    radius = entity.dxf.radius
    cx, cy = center.x, center.y
    center_qt = to_qt(cx, cy)

    dx = cursor.x() - center_qt.x()
    dy = -(cursor.y() - center_qt.y())
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return radius

    angle = math.degrees(math.atan2(dy, dx)) % 360.0
    start = entity.dxf.start_angle % 360.0
    end = entity.dxf.end_angle % 360.0

    if start <= end:
        on_arc = start <= angle <= end
    else:
        on_arc = angle >= start or angle <= end

    if on_arc:
        return abs(dist - radius)

    start_rad = math.radians(start)
    end_rad = math.radians(end)
    p1 = to_qt(cx + radius * math.cos(start_rad), cy + radius * math.sin(start_rad))
    p2 = to_qt(cx + radius * math.cos(end_rad), cy + radius * math.sin(end_rad))
    return min(
        math.hypot(cursor.x() - p1.x(), cursor.y() - p1.y()),
        math.hypot(cursor.x() - p2.x(), cursor.y() - p2.y()),
    )
