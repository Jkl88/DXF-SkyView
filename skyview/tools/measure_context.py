"""Контекст точки измерения без явной привязки."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtCore import QPointF, QRectF

from skyview.dxf.loader import EntityRecord
from skyview.tools.snap import (
    SnapMode,
    SnapResult,
    SnapSettings,
    find_nearest_line_segment,
    _dist,
    _entity_centers,
    _nearest_on_segment,
    _to_qt,
)


class MeasureContextType(Enum):
    FREE = auto()
    LINE = auto()
    CIRCLE = auto()


@dataclass
class MeasurePointContext:
    point: QPointF
    context_type: MeasureContextType = MeasureContextType.FREE
    line_a: QPointF | None = None
    line_b: QPointF | None = None
    line2_a: QPointF | None = None
    line2_b: QPointF | None = None
    circle_center: QPointF | None = None
    circle_radius: float = 0.0
    circle_handle: str | None = None
    line_handle: str | None = None
    snapped: bool = False
    apparent_intersection: bool = False


def circle_center_for_handle(
    records: list[EntityRecord], handle: str | None
) -> tuple[QPointF, float, str] | None:
    """Центр окружности/дуги по handle объекта."""
    if not handle:
        return None
    for record in records:
        if record.handle != handle:
            continue
        entity = record.entity
        if entity.dxftype() not in ("CIRCLE", "ARC"):
            return None
        centers = _entity_centers(record)
        if not centers:
            return None
        return centers[0], entity.dxf.radius, record.handle
    return None


def _detect_line_at(
    cursor: QPointF, records: list[EntityRecord], tol: float
) -> MeasurePointContext | None:
    hit = find_nearest_line_segment(cursor, records, tol)
    if hit is None:
        return None
    foot, la, lb, _, handle = hit
    return MeasurePointContext(
        point=foot,
        context_type=MeasureContextType.LINE,
        line_a=la,
        line_b=lb,
        line_handle=handle,
    )


def _point_on_arc_toward(entity, cursor: QPointF) -> QPointF | None:
    c = entity.dxf.center
    r = entity.dxf.radius
    px, py = cursor.x(), -cursor.y()
    ang = math.degrees(math.atan2(py - c.y, px - c.x)) % 360
    sa = entity.dxf.start_angle % 360
    ea = entity.dxf.end_angle % 360
    if sa <= ea:
        if not (sa <= ang <= ea):
            return None
    elif not (ang >= sa or ang <= ea):
        return None
    rad = math.radians(ang)
    return _to_qt(c.x + r * math.cos(rad), c.y + r * math.sin(rad))


def _nearest_on_circle(cursor: QPointF, center: QPointF, radius: float) -> QPointF:
    cx, cy = center.x(), -center.y()
    px, py = cursor.x(), -cursor.y()
    ang = math.atan2(py - cy, px - cx)
    return _to_qt(cx + radius * math.cos(ang), cy + radius * math.sin(ang))


def _distance_to_circumference(point: QPointF, center: QPointF, radius: float) -> float:
    return abs(_dist(point, center) - radius)


def _detect_circle_at(
    cursor: QPointF, records: list[EntityRecord], tol: float
) -> MeasurePointContext | None:
    best: tuple[QPointF, QPointF, float, float, str] | None = None

    for record in records:
        entity = record.entity
        t = entity.dxftype()
        if t not in ("CIRCLE", "ARC"):
            continue
        centers = _entity_centers(record)
        if not centers:
            continue
        center = centers[0]
        r = entity.dxf.radius
        dist_center = _dist(cursor, center)

        if dist_center <= tol:
            hit = center
            d = dist_center
        elif t == "ARC":
            hit = _point_on_arc_toward(entity, cursor)
            if hit is None:
                continue
            d = _dist(cursor, hit)
        else:
            d = _distance_to_circumference(cursor, center, r)
            if d > tol:
                continue
            hit = _nearest_on_circle(cursor, center, r)

        if best is None or d < best[3]:
            best = (hit, center, r, d, record.handle)

    if best is None or best[3] > tol:
        return None

    _, center, r, _, handle = best
    return MeasurePointContext(
        point=center,
        context_type=MeasureContextType.CIRCLE,
        circle_center=center,
        circle_radius=r,
        circle_handle=handle,
    )


def resolve_measure_point(
    cursor_scene: QPointF,
    records: list[EntityRecord],
    snap: SnapResult | None,
    scale: float,
    snap_settings: SnapSettings,
    hit_tol_px: float = 14.0,
) -> MeasurePointContext:
    """Определить точку измерения и контекст линии / окружности."""
    tol = hit_tol_px / max(scale, 1e-6)

    if snap is not None:
        if snap.mode == SnapMode.APPARENT_INTERSECTION:
            return MeasurePointContext(
                point=snap.point,
                snapped=True,
                apparent_intersection=True,
                line_a=snap.ref_line_a,
                line_b=snap.ref_line_b,
                line2_a=snap.ref_line2_a,
                line2_b=snap.ref_line2_b,
            )
        if snap.mode == SnapMode.LINE:
            if snap.ref_line_a is not None and snap.ref_line_b is not None:
                return MeasurePointContext(
                    point=snap.point,
                    context_type=MeasureContextType.LINE,
                    line_a=snap.ref_line_a,
                    line_b=snap.ref_line_b,
                    line_handle=snap.ref_handle,
                    snapped=True,
                )
        if snap.mode == SnapMode.CENTER:
            for record in records:
                if record.entity.dxftype() in ("CIRCLE", "ARC"):
                    centers = _entity_centers(record)
                    if centers and _dist(snap.point, centers[0]) < 1e-6:
                        center = centers[0]
                        return MeasurePointContext(
                            point=snap.point,
                            context_type=MeasureContextType.CIRCLE,
                            circle_center=center,
                            circle_radius=record.entity.dxf.radius,
                            circle_handle=record.handle,
                            snapped=True,
                        )
        if snap.mode == SnapMode.RADIAL and snap_settings.is_enabled(SnapMode.CENTER):
            hit = circle_center_for_handle(records, snap.ref_handle)
            if hit is not None:
                center, radius, handle = hit
                return MeasurePointContext(
                    point=center,
                    context_type=MeasureContextType.CIRCLE,
                    circle_center=center,
                    circle_radius=radius,
                    circle_handle=handle,
                    snapped=True,
                )
        return MeasurePointContext(point=snap.point, snapped=True)

    line_ctx = (
        _detect_line_at(cursor_scene, records, tol)
        if snap_settings.is_enabled(SnapMode.LINE)
        else None
    )
    circle_ctx = (
        _detect_circle_at(cursor_scene, records, tol)
        if snap_settings.is_enabled(SnapMode.CENTER)
        else None
    )

    if circle_ctx and line_ctx:
        la, lb = line_ctx.line_a, line_ctx.line_b
        line_d = (
            _dist(cursor_scene, _nearest_on_segment(cursor_scene, la, lb))
            if la is not None and lb is not None
            else float("inf")
        )
        cc = circle_ctx.circle_center
        circle_d = (
            _distance_to_circumference(cursor_scene, cc, circle_ctx.circle_radius)
            if cc is not None
            else float("inf")
        )
        geo = circle_ctx if circle_d + 1e-9 < line_d else line_ctx
    elif line_ctx:
        geo = line_ctx
    elif circle_ctx:
        geo = circle_ctx
    else:
        geo = None

    if geo is not None:
        return geo

    return MeasurePointContext(point=cursor_scene)


def is_valid_measure_point(ctx: MeasurePointContext) -> bool:
    """Точку можно ставить только на геометрию или привязку."""
    if ctx.context_type != MeasureContextType.FREE:
        return True
    return ctx.snapped or ctx.apparent_intersection


def apparent_guide_segment(
    inter: QPointF, line_a: QPointF, line_b: QPointF
) -> tuple[QPointF, QPointF] | None:
    """Отрезок пунктира от прямого ребра к условному пересечению."""
    foot = project_on_line(inter, line_a, line_b)
    t = line_parameter(foot, line_a, line_b)
    if t > 1.0 + 1e-4:
        return line_b, foot
    if t < -1e-4:
        return foot, line_a
    if _dist(line_a, inter) >= _dist(line_b, inter):
        return line_b, foot
    return line_a, foot


def apparent_intersection_fits_view(
    inter: QPointF,
    la1: QPointF,
    lb1: QPointF,
    la2: QPointF,
    lb2: QPointF,
    visible: QRectF,
) -> bool:
    """Условное пересечение — если точка пересечения и опорные точки пунктира в кадре."""
    if visible.isEmpty() or not visible.contains(inter):
        return False
    for la, lb in ((la1, lb1), (la2, lb2)):
        seg = apparent_guide_segment(inter, la, lb)
        if seg is None:
            return False
        if not visible.contains(seg[0]):
            return False
    return True


def project_on_line(point: QPointF, line_a: QPointF, line_b: QPointF) -> QPointF:
    dx, dy = line_b.x() - line_a.x(), line_b.y() - line_a.y()
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return QPointF(line_a)
    t = ((point.x() - line_a.x()) * dx + (point.y() - line_a.y()) * dy) / len_sq
    return QPointF(line_a.x() + t * dx, line_a.y() + t * dy)


def perpendicular_distance(point: QPointF, line_a: QPointF, line_b: QPointF) -> float:
    foot = project_on_line(point, line_a, line_b)
    return math.hypot(point.x() - foot.x(), point.y() - foot.y())


def line_direction(line_a: QPointF, line_b: QPointF) -> tuple[float, float]:
    dx = line_b.x() - line_a.x()
    dy = line_b.y() - line_a.y()
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return 1.0, 0.0
    return dx / length, dy / length


def lines_parallel(
    la1: QPointF, lb1: QPointF, la2: QPointF, lb2: QPointF, tol: float = 1e-4
) -> bool:
    dx1, dy1 = line_direction(la1, lb1)
    dx2, dy2 = line_direction(la2, lb2)
    return abs(dx1 * dy2 - dy1 * dx2) < tol


def lines_collinear(
    la1: QPointF, lb1: QPointF, la2: QPointF, lb2: QPointF, tol: float = 1e-4
) -> bool:
    if not lines_parallel(la1, lb1, la2, lb2, tol):
        return False
    return perpendicular_distance(la2, la1, lb1) < tol


def line_intersection(
    la1: QPointF, lb1: QPointF, la2: QPointF, lb2: QPointF
) -> QPointF | None:
    x1, y1 = la1.x(), la1.y()
    x2, y2 = lb1.x(), lb1.y()
    x3, y3 = la2.x(), la2.y()
    x4, y4 = lb2.x(), lb2.y()
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return QPointF(x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def ray_angle_at_intersection(
    inter: QPointF, point: QPointF, line_a: QPointF, line_b: QPointF
) -> float:
    dx, dy = line_direction(line_a, line_b)
    vx = point.x() - inter.x()
    vy = point.y() - inter.y()
    if dx * vx + dy * vy < 0:
        dx, dy = -dx, -dy
    return math.atan2(dy, dx)


def angle_between_rays(ang_a: float, ang_b: float) -> tuple[float, float, float]:
    """Вернуть (start_angle, span, angle_deg) для дуги 0..180°."""
    diff = ang_b - ang_a
    while diff <= -math.pi:
        diff += 2 * math.pi
    while diff > math.pi:
        diff -= 2 * math.pi
    if diff < 0:
        start, span = ang_b, -diff
    else:
        start, span = ang_a, diff
    return start, span, math.degrees(span)


def line_parameter(point: QPointF, line_a: QPointF, line_b: QPointF) -> float:
    dx, dy = line_b.x() - line_a.x(), line_b.y() - line_a.y()
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return 0.0
    return ((point.x() - line_a.x()) * dx + (point.y() - line_a.y()) * dy) / len_sq


def point_on_segment(point: QPointF, line_a: QPointF, line_b: QPointF, tol: float = 1e-4) -> bool:
    return -tol <= line_parameter(point, line_a, line_b) <= 1.0 + tol


def clip_to_segment(point: QPointF, line_a: QPointF, line_b: QPointF) -> QPointF:
    t = line_parameter(point, line_a, line_b)
    t = max(0.0, min(1.0, t))
    return QPointF(
        line_a.x() + t * (line_b.x() - line_a.x()),
        line_a.y() + t * (line_b.y() - line_a.y()),
    )


def extension_on_line_toward_inter(
    inter: QPointF, line_a: QPointF, line_b: QPointF, pick: QPointF
) -> tuple[QPointF, QPointF] | None:
    """Отрезок на линии от точки измерения в сторону условного пересечения."""
    foot_p = project_on_line(pick, line_a, line_b)
    foot_i = project_on_line(inter, line_a, line_b)
    t_p = line_parameter(foot_p, line_a, line_b)
    t_i = line_parameter(foot_i, line_a, line_b)
    if t_i >= t_p:
        t_start, t_end = max(0.0, min(1.0, t_p)), max(0.0, min(1.0, t_i))
    else:
        t_start, t_end = max(0.0, min(1.0, t_i)), max(0.0, min(1.0, t_p))
    if t_end - t_start < 1e-9:
        return None
    dx, dy = line_b.x() - line_a.x(), line_b.y() - line_a.y()
    return (
        QPointF(line_a.x() + dx * t_start, line_a.y() + dy * t_start),
        QPointF(line_a.x() + dx * t_end, line_a.y() + dy * t_end),
    )


def is_apparent_intersection(
    inter: QPointF, la1: QPointF, lb1: QPointF, la2: QPointF, lb2: QPointF
) -> bool:
    return not (
        point_on_segment(inter, la1, lb1) and point_on_segment(inter, la2, lb2)
    )
