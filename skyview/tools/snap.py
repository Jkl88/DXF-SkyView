"""Система привязок (OSNAP)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto

from PySide6.QtCore import QPointF, QRectF

from skyview.dxf.loader import EntityRecord


class SnapMode(Enum):
    ENDPOINT = auto()
    MIDPOINT = auto()
    CENTER = auto()
    QUADRANT = auto()
    INTERSECTION = auto()
    APPARENT_INTERSECTION = auto()
    LINE = auto()
    NEAREST = auto()
    RADIAL = auto()


SNAP_LABELS: dict[SnapMode, str] = {
    SnapMode.ENDPOINT: "Конечная точка",
    SnapMode.MIDPOINT: "Середина",
    SnapMode.CENTER: "Центр",
    SnapMode.QUADRANT: "Квадрант",
    SnapMode.INTERSECTION: "Пересечение",
    SnapMode.APPARENT_INTERSECTION: "Условное пересечение",
    SnapMode.LINE: "Линия",
    SnapMode.NEAREST: "Ближайшая",
    SnapMode.RADIAL: "На окружности (радиус)",
}


# Порядок по умолчанию в диалоге «Привязки». Чем выше в списке — тем выше приоритет.
DEFAULT_SNAP_PRIORITY: list[SnapMode] = [
    SnapMode.CENTER,
    SnapMode.ENDPOINT,
    SnapMode.MIDPOINT,
    SnapMode.INTERSECTION,
    SnapMode.APPARENT_INTERSECTION,
    SnapMode.QUADRANT,
    SnapMode.RADIAL,
    SnapMode.LINE,
    SnapMode.NEAREST,
]


# Конечная точка — чуть больший радиус захвата, чем у остальных привязок.
ENDPOINT_TOLERANCE_SCALE = 1.4
MIDPOINT_TOLERANCE_SCALE = 1.35


@dataclass
class SnapResult:
    point: QPointF
    mode: SnapMode
    distance: float
    ref_line_a: QPointF | None = None
    ref_line_b: QPointF | None = None
    ref_line2_a: QPointF | None = None
    ref_line2_b: QPointF | None = None
    ref_handle: str | None = None
    ref_handle2: str | None = None


@dataclass
class SnapSettings:
    enabled: dict[SnapMode, bool] = field(default_factory=lambda: {m: True for m in SnapMode})
    tolerance_px: float = 12.0
    priority: list[SnapMode] = field(default_factory=lambda: list(DEFAULT_SNAP_PRIORITY))

    def is_enabled(self, mode: SnapMode) -> bool:
        return self.enabled.get(mode, False)

    def priority_rank(self, mode: SnapMode) -> int:
        try:
            return self.priority.index(mode)
        except ValueError:
            return len(self.priority) + 99


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _to_qt(x: float, y: float) -> QPointF:
    return QPointF(x, -y)


def _entity_endpoints(record: EntityRecord) -> list[QPointF]:
    entity = record.entity
    t = entity.dxftype()
    pts: list[QPointF] = []

    if t == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        pts.extend([_to_qt(s.x, s.y), _to_qt(e.x, e.y)])
    elif t in ("ARC", "CIRCLE"):
        c = entity.dxf.center
        r = entity.dxf.radius
        if t == "ARC":
            sa = math.radians(entity.dxf.start_angle)
            ea = math.radians(entity.dxf.end_angle)
            pts.append(_to_qt(c.x + r * math.cos(sa), c.y + r * math.sin(sa)))
            pts.append(_to_qt(c.x + r * math.cos(ea), c.y + r * math.sin(ea)))
    elif t == "LWPOLYLINE":
        for x, y, *_ in entity.get_points("xyseb"):
            pts.append(_to_qt(x, y))
    elif t == "POLYLINE":
        for v in entity.vertices:
            loc = v.dxf.location
            pts.append(_to_qt(loc.x, loc.y))
    elif t == "POINT":
        loc = entity.dxf.location
        pts.append(_to_qt(loc.x, loc.y))

    return pts


def _entity_midpoints(record: EntityRecord) -> list[QPointF]:
    entity = record.entity
    t = entity.dxftype()
    pts: list[QPointF] = []

    if t in ("LINE", "LWPOLYLINE", "POLYLINE"):
        for a, b in _collect_line_segments(record):
            pts.append(QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
    elif t == "ARC":
        c = entity.dxf.center
        r = entity.dxf.radius
        sa = math.radians(entity.dxf.start_angle)
        ea = math.radians(entity.dxf.end_angle)
        mid = (sa + ea) / 2
        pts.append(_to_qt(c.x + r * math.cos(mid), c.y + r * math.sin(mid)))

    return pts


def _entity_centers(record: EntityRecord) -> list[QPointF]:
    entity = record.entity
    t = entity.dxftype()
    if t in ("CIRCLE", "ARC", "ELLIPSE"):
        c = entity.dxf.center
        return [_to_qt(c.x, c.y)]
    return []


def _entity_quadrants(record: EntityRecord) -> list[QPointF]:
    entity = record.entity
    t = entity.dxftype()
    if t not in ("CIRCLE", "ARC"):
        return []
    c = entity.dxf.center
    r = entity.dxf.radius
    return [
        _to_qt(c.x + r, c.y),
        _to_qt(c.x, c.y + r),
        _to_qt(c.x - r, c.y),
        _to_qt(c.x, c.y - r),
    ]


def _nearest_on_segment(cursor: QPointF, a: QPointF, b: QPointF) -> QPointF:
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return a
    t = max(0, min(1, ((cursor.x() - ax) * dx + (cursor.y() - ay) * dy) / len_sq))
    return QPointF(ax + t * dx, ay + t * dy)


def _nearest_on_record(cursor: QPointF, record: EntityRecord) -> QPointF | None:
    path = record.path
    if path.isEmpty():
        return None
    best = None
    best_d = float("inf")
    # Сэмплируем точки пути
    poly = path.toFillPolygon()
    for i in range(len(poly) - 1):
        pt = _nearest_on_segment(cursor, poly[i], poly[i + 1])
        d = _dist(cursor, pt)
        if d < best_d:
            best_d = d
            best = pt
    return best


def _line_intersection(
    a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF
) -> QPointF | None:
    x1, y1, x2, y2 = a1.x(), a1.y(), a2.x(), a2.y()
    x3, y3, x4, y4 = b1.x(), b1.y(), b2.x(), b2.y()
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        return QPointF(x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _infinite_line_intersection(
    a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF
) -> QPointF | None:
    x1, y1, x2, y2 = a1.x(), a1.y(), a2.x(), a2.y()
    x3, y3, x4, y4 = b1.x(), b1.y(), b2.x(), b2.y()
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return QPointF(x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _line_parameter(point: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return 0.0
    return ((point.x() - a.x()) * dx + (point.y() - a.y()) * dy) / len_sq


def _point_on_segment(point: QPointF, a: QPointF, b: QPointF, tol: float = 1e-4) -> bool:
    t = _line_parameter(point, a, b)
    return -tol <= t <= 1.0 + tol


def _collect_line_segments(record: EntityRecord) -> list[tuple[QPointF, QPointF]]:
    entity = record.entity
    t = entity.dxftype()
    segs: list[tuple[QPointF, QPointF]] = []

    if t == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        segs.append((_to_qt(s.x, s.y), _to_qt(e.x, e.y)))
    elif t == "LWPOLYLINE":
        points = list(entity.get_points("xy"))
        for i in range(len(points) - 1):
            segs.append(
                (_to_qt(points[i][0], points[i][1]), _to_qt(points[i + 1][0], points[i + 1][1]))
            )
        if entity.closed and len(points) > 1:
            segs.append(
                (_to_qt(points[-1][0], points[-1][1]), _to_qt(points[0][0], points[0][1]))
            )
    elif t == "POLYLINE":
        verts = [v.dxf.location for v in entity.vertices]
        for i in range(len(verts) - 1):
            segs.append(
                (_to_qt(verts[i].x, verts[i].y), _to_qt(verts[i + 1].x, verts[i + 1].y))
            )
        if entity.is_closed and len(verts) > 1:
            segs.append(
                (_to_qt(verts[-1].x, verts[-1].y), _to_qt(verts[0].x, verts[0].y))
            )
    return segs


def _nearest_on_path_segment(
    cursor: QPointF, record: EntityRecord
) -> tuple[QPointF, QPointF, QPointF, float] | None:
    path = record.path
    if path.isEmpty():
        return None
    poly = path.toFillPolygon()
    best: tuple[QPointF, QPointF, QPointF, float] | None = None
    for i in range(len(poly) - 1):
        seg_a, seg_b = poly[i], poly[i + 1]
        foot = _nearest_on_segment(cursor, seg_a, seg_b)
        d = _dist(cursor, foot)
        if best is None or d < best[3]:
            best = (foot, seg_a, seg_b, d)
    return best


def find_nearest_line_segment(
    cursor: QPointF, records: list[EntityRecord], tol: float
) -> tuple[QPointF, QPointF, QPointF, float, str] | None:
    """Ближайшая точка на прямом сегменте. (foot, line_a, line_b, distance, handle)."""
    best: tuple[QPointF, QPointF, QPointF, float] | None = None
    best_handle: str | None = None

    for record in records:
        entity = record.entity
        if entity.dxftype() in ("CIRCLE", "ARC"):
            continue

        hit = _nearest_on_path_segment(cursor, record)
        if hit and (best is None or hit[3] < best[3]):
            best = hit
            best_handle = record.handle

        t = entity.dxftype()
        if t == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            a, b = _to_qt(s.x, s.y), _to_qt(e.x, e.y)
            foot = _nearest_on_segment(cursor, a, b)
            d = _dist(cursor, foot)
            if d <= tol and (best is None or d < best[3]):
                best = (foot, a, b, d)
                best_handle = record.handle
        elif t in ("LWPOLYLINE", "POLYLINE"):
            for a, b in _collect_line_segments(record):
                foot = _nearest_on_segment(cursor, a, b)
                d = _dist(cursor, foot)
                if d <= tol and (best is None or d < best[3]):
                    best = (foot, a, b, d)
                    best_handle = record.handle

    if best is None or best[3] > tol or best_handle is None:
        return None
    return best[0], best[1], best[2], best[3], best_handle


def _radial_on_circle(cursor: QPointF, center: QPointF, radius: float) -> QPointF:
    """Точка на окружности по лучу центр → курсор."""
    cx, cy = center.x(), -center.y()
    px, py = cursor.x(), -cursor.y()
    ang = math.atan2(py - cy, px - cx)
    return _to_qt(cx + radius * math.cos(ang), cy + radius * math.sin(ang))


def _radial_on_arc(cursor: QPointF, entity) -> QPointF | None:
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


class SnapEngine:
    def __init__(self, settings: SnapSettings | None = None):
        self.settings = settings or SnapSettings()
        self._records: list[EntityRecord] = []

    def set_records(self, records: list[EntityRecord]) -> None:
        self._records = records

    def snap(
        self,
        cursor_scene: QPointF,
        scale: float,
        visible_rect: QRectF | None = None,
    ) -> SnapResult | None:
        """Найти ближайшую привязку. scale = пикселей на единицу чертежа."""
        tol = self.settings.tolerance_px / max(scale, 1e-6)
        endpoint_tol = tol * ENDPOINT_TOLERANCE_SCALE
        midpoint_tol = tol * MIDPOINT_TOLERANCE_SCALE
        candidates: list[SnapResult] = []

        for record in self._records:
            if self.settings.is_enabled(SnapMode.ENDPOINT):
                for pt in _entity_endpoints(record):
                    d = _dist(cursor_scene, pt)
                    if d <= endpoint_tol:
                        candidates.append(SnapResult(pt, SnapMode.ENDPOINT, d))

            if self.settings.is_enabled(SnapMode.MIDPOINT):
                for pt in _entity_midpoints(record):
                    d = _dist(cursor_scene, pt)
                    if d <= midpoint_tol:
                        candidates.append(
                            SnapResult(
                                pt,
                                SnapMode.MIDPOINT,
                                d,
                                ref_handle=record.handle,
                            )
                        )

            if self.settings.is_enabled(SnapMode.CENTER):
                for pt in _entity_centers(record):
                    d = _dist(cursor_scene, pt)
                    if d <= tol:
                        candidates.append(
                            SnapResult(
                                pt,
                                SnapMode.CENTER,
                                d,
                                ref_handle=record.handle,
                            )
                        )

            if self.settings.is_enabled(SnapMode.QUADRANT):
                for pt in _entity_quadrants(record):
                    d = _dist(cursor_scene, pt)
                    if d <= tol:
                        candidates.append(
                            SnapResult(
                                pt,
                                SnapMode.QUADRANT,
                                d,
                                ref_handle=record.handle,
                            )
                        )

            if self.settings.is_enabled(SnapMode.RADIAL):
                entity = record.entity
                if entity.dxftype() == "CIRCLE":
                    c = entity.dxf.center
                    center = _to_qt(c.x, c.y)
                    pt = _radial_on_circle(cursor_scene, center, entity.dxf.radius)
                    d = _dist(cursor_scene, pt)
                    if d <= tol:
                        candidates.append(
                            SnapResult(
                                pt,
                                SnapMode.RADIAL,
                                d,
                                ref_handle=record.handle,
                            )
                        )
                elif entity.dxftype() == "ARC":
                    pt = _radial_on_arc(cursor_scene, entity)
                    if pt:
                        d = _dist(cursor_scene, pt)
                        if d <= tol:
                            candidates.append(
                                SnapResult(
                                    pt,
                                    SnapMode.RADIAL,
                                    d,
                                    ref_handle=record.handle,
                                )
                            )

            if self.settings.is_enabled(SnapMode.NEAREST):
                pt = _nearest_on_record(cursor_scene, record)
                if pt:
                    d = _dist(cursor_scene, pt)
                    if d <= tol:
                        candidates.append(SnapResult(pt, SnapMode.NEAREST, d))

        if self.settings.is_enabled(SnapMode.LINE):
            hit = find_nearest_line_segment(cursor_scene, self._records, tol)
            if hit:
                foot, la, lb, d, handle = hit
                candidates.append(
                    SnapResult(
                        foot,
                        SnapMode.LINE,
                        d,
                        ref_line_a=la,
                        ref_line_b=lb,
                        ref_handle=handle,
                    )
                )

        if self.settings.is_enabled(SnapMode.INTERSECTION):
            segments: list[tuple[QPointF, QPointF, str]] = []
            for record in self._records:
                for a, b in _collect_line_segments(record):
                    segments.append((a, b, record.handle))
            for i in range(len(segments)):
                for j in range(i + 1, len(segments)):
                    s1a, s1b, h1 = segments[i]
                    s2a, s2b, h2 = segments[j]
                    pt = _line_intersection(s1a, s1b, s2a, s2b)
                    if pt:
                        d = _dist(cursor_scene, pt)
                        if d <= tol:
                            candidates.append(
                                SnapResult(
                                    pt,
                                    SnapMode.INTERSECTION,
                                    d,
                                    ref_handle=h1,
                                    ref_handle2=h2,
                                )
                            )

        if self.settings.is_enabled(SnapMode.APPARENT_INTERSECTION):
            from skyview.tools.measure_context import apparent_intersection_fits_view

            segments = []
            for record in self._records:
                segments.extend(_collect_line_segments(record))
            for i in range(len(segments)):
                for j in range(i + 1, len(segments)):
                    s1, s2 = segments[i], segments[j]
                    pt = _infinite_line_intersection(s1[0], s1[1], s2[0], s2[1])
                    if pt is None:
                        continue
                    if _point_on_segment(pt, s1[0], s1[1]) and _point_on_segment(pt, s2[0], s2[1]):
                        continue
                    if visible_rect is not None and not apparent_intersection_fits_view(
                        pt, s1[0], s1[1], s2[0], s2[1], visible_rect
                    ):
                        continue
                    d = _dist(cursor_scene, pt)
                    if d <= tol:
                        candidates.append(
                            SnapResult(
                                pt,
                                SnapMode.APPARENT_INTERSECTION,
                                d,
                                ref_line_a=s1[0],
                                ref_line_b=s1[1],
                                ref_line2_a=s2[0],
                                ref_line2_b=s2[1],
                            )
                        )

        if not candidates:
            return None

        candidates.sort(
            key=lambda c: (self.settings.priority_rank(c.mode), c.distance)
        )
        return candidates[0]
