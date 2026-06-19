"""Сегменты сущностей для выбора и привязок."""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath

from ezdxf.entities import DXFEntity


def to_qt(x: float, y: float) -> QPointF:
    return QPointF(x, -y)


def collect_line_segments_for_entity(entity: DXFEntity) -> list[tuple[QPointF, QPointF]]:
    t = entity.dxftype()
    segs: list[tuple[QPointF, QPointF]] = []

    if t == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        segs.append((to_qt(s.x, s.y), to_qt(e.x, e.y)))
    elif t == "LWPOLYLINE":
        points = list(entity.get_points("xy"))
        for i in range(len(points) - 1):
            segs.append(
                (to_qt(points[i][0], points[i][1]), to_qt(points[i + 1][0], points[i + 1][1]))
            )
        if entity.closed and len(points) > 1:
            segs.append(
                (to_qt(points[-1][0], points[-1][1]), to_qt(points[0][0], points[0][1]))
            )
    elif t == "POLYLINE":
        verts = [v.dxf.location for v in entity.vertices]
        for i in range(len(verts) - 1):
            segs.append(
                (to_qt(verts[i].x, verts[i].y), to_qt(verts[i + 1].x, verts[i + 1].y))
            )
        if entity.is_closed and len(verts) > 1:
            segs.append(
                (to_qt(verts[-1].x, verts[-1].y), to_qt(verts[0].x, verts[0].y))
            )
    return segs


def nearest_on_segment(cursor: QPointF, a: QPointF, b: QPointF) -> QPointF:
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return a
    t = max(0.0, min(1.0, ((cursor.x() - a.x()) * dx + (cursor.y() - a.y()) * dy) / len_sq))
    return QPointF(a.x() + t * dx, a.y() + t * dy)


def path_to_pick_segments(path: QPainterPath) -> list[tuple[QPointF, QPointF]]:
    segments: list[tuple[QPointF, QPointF]] = []
    current: QPointF | None = None
    for i in range(path.elementCount()):
        el = path.elementAt(i)
        if el.type == QPainterPath.ElementType.MoveToElement:
            current = QPointF(el.x, el.y)
        elif el.type == QPainterPath.ElementType.LineToElement and current is not None:
            nxt = QPointF(el.x, el.y)
            segments.append((current, nxt))
            current = nxt
    return segments


def nearest_pick_distance(
    cursor: QPointF, segments: list[tuple[QPointF, QPointF]]
) -> float | None:
    if not segments:
        return None
    best = float("inf")
    for a, b in segments:
        foot = nearest_on_segment(cursor, a, b)
        dx = cursor.x() - foot.x()
        dy = cursor.y() - foot.y()
        best = min(best, (dx * dx + dy * dy) ** 0.5)
    return best


def point_near_segments(cursor: QPointF, segments: list[tuple[QPointF, QPointF]], tol: float) -> bool:
    dist = nearest_pick_distance(cursor, segments)
    return dist is not None and dist <= tol
