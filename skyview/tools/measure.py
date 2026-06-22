"""Инструмент измерения."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView

from skyview.canvas.screen_overlay import draw_screen_dot, draw_screen_label
from skyview.dxf.units import format_length
from skyview.tools.measure_context import (
    MeasureContextType,
    MeasurePointContext,
    angle_between_rays,
    apparent_guide_segment,
    clip_to_segment,
    extension_on_line_toward_inter,
    is_apparent_intersection,
    line_intersection,
    lines_collinear,
    lines_parallel,
    perpendicular_distance,
    project_on_line,
    ray_angle_at_intersection,
)

ALIGN_TOL = 1e-4
REF_LINE_COLOR = QColor(100, 180, 255, 180)


@dataclass
class MeasureState:
    point_a: MeasurePointContext | None = None
    point_b: MeasurePointContext | None = None
    cursor: MeasurePointContext | None = None
    phase: int = 0  # 0=ожидание A, 1=ожидание B
    done_a: MeasurePointContext | None = None
    done_b: MeasurePointContext | None = None


class MeasureOverlay(QGraphicsItem):
    """Оверлей измерения: точки, треугольник, подписи."""

    Z_VALUE = 1000
    DOT_RADIUS = 3.0
    FONT_SIZE = 9

    def __init__(self, unit: str = "mm"):
        super().__init__()
        self.unit = unit
        self.state = MeasureState()
        self.setZValue(self.Z_VALUE)

    def set_unit(self, unit: str) -> None:
        self.unit = unit
        self.update()

    def reset(self) -> None:
        self.state = MeasureState()
        self.update()

    def set_point_a(self, ctx: MeasurePointContext) -> None:
        self.state.done_a = None
        self.state.done_b = None
        self.state.point_a = ctx
        self.state.point_b = None
        self.state.phase = 1
        self.update()

    def set_point_b(self, ctx: MeasurePointContext) -> None:
        self.state.done_a = self.state.point_a
        self.state.done_b = ctx
        self.state.point_a = None
        self.state.point_b = None
        self.state.phase = 0
        self.update()

    def set_cursor(self, ctx: MeasurePointContext | None) -> None:
        self.state.cursor = ctx
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-1e6, -1e6, 2e6, 2e6)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        s = self.state
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        visible = self._visible_scene_rect(option, widget)

        if s.done_a and s.done_b:
            self._draw_measurement(painter, s.done_a, s.done_b, visible)

        if s.phase == 0 and s.cursor:
            self._draw_apparent_guides(painter, s.cursor)
            if s.cursor.context_type == MeasureContextType.LINE:
                self._draw_ref_line(painter, s.cursor)
            draw_screen_dot(painter, s.cursor.point, self.DOT_RADIUS, QColor(46, 204, 113))
        elif s.phase == 1:
            if s.point_a:
                self._draw_apparent_guides(painter, s.point_a)
                if s.point_a.context_type == MeasureContextType.LINE:
                    self._draw_ref_line(painter, s.point_a)
                draw_screen_dot(painter, s.point_a.point, self.DOT_RADIUS, QColor(46, 204, 113))
            if s.cursor:
                self._draw_apparent_guides(painter, s.cursor)
                if s.cursor.context_type == MeasureContextType.LINE:
                    self._draw_ref_line(painter, s.cursor)
                draw_screen_dot(painter, s.cursor.point, self.DOT_RADIUS, QColor(230, 126, 34))

    @staticmethod
    def _scene_pixels(painter: QPainter, px: float) -> float:
        scale = abs(painter.worldTransform().m11()) or 1.0
        return px / scale

    @staticmethod
    def _trim_segment(
        a: QPointF, b: QPointF, trim_a: float, trim_b: float
    ) -> tuple[QPointF, QPointF]:
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        length = math.hypot(dx, dy)
        if length < trim_a + trim_b + 1e-9:
            return a, b
        ux, uy = dx / length, dy / length
        return (
            QPointF(a.x() + ux * trim_a, a.y() + uy * trim_a),
            QPointF(b.x() - ux * trim_b, b.y() - uy * trim_b),
        )

    def _dot_trim(self, painter: QPainter) -> float:
        return self._scene_pixels(painter, self.DOT_RADIUS)

    @staticmethod
    def _visible_scene_rect(option, widget) -> QRectF | None:
        if widget is not None:
            view = widget
            if not isinstance(view, QGraphicsView):
                parent = widget.parentWidget() if hasattr(widget, "parentWidget") else None
                while parent is not None:
                    if isinstance(parent, QGraphicsView):
                        view = parent
                        break
                    parent = parent.parentWidget()
            if isinstance(view, QGraphicsView):
                return view.mapToScene(view.viewport().rect()).boundingRect()
        if option is not None and hasattr(option, "exposedRect"):
            exposed = option.exposedRect
            if not exposed.isEmpty():
                return exposed
        return None

    @staticmethod
    def _clamp_to_visible(
        point: QPointF, visible: QRectF | None, painter: QPainter
    ) -> QPointF:
        if visible is None or visible.isEmpty() or visible.contains(point):
            return point
        margin = MeasureOverlay._scene_pixels(painter, 24)
        area = visible.adjusted(margin, margin, -margin, -margin)
        if area.isEmpty():
            area = visible
        x = max(area.left(), min(area.right(), point.x()))
        y = max(area.top(), min(area.bottom(), point.y()))
        return QPointF(x, y)

    @staticmethod
    def _arc_radius_to_picks(
        inter: QPointF,
        point_a: QPointF,
        la1: QPointF,
        lb1: QPointF,
        point_b: QPointF,
        la2: QPointF,
        lb2: QPointF,
    ) -> float:
        foot_a = project_on_line(point_a, la1, lb1)
        foot_b = project_on_line(point_b, la2, lb2)
        r_a = math.hypot(foot_a.x() - inter.x(), foot_a.y() - inter.y())
        r_b = math.hypot(foot_b.x() - inter.x(), foot_b.y() - inter.y())
        return min(r_a, r_b)

    @staticmethod
    def _draw_apparent_guides(painter: QPainter, ctx: MeasurePointContext) -> None:
        if not ctx.apparent_intersection:
            return
        if (
            ctx.line_a is None
            or ctx.line_b is None
            or ctx.line2_a is None
            or ctx.line2_b is None
        ):
            return
        pen = QPen(QColor(210, 210, 210, 220), 1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for la, lb in ((ctx.line_a, ctx.line_b), (ctx.line2_a, ctx.line2_b)):
            seg = apparent_guide_segment(ctx.point, la, lb)
            if seg is not None:
                painter.drawLine(seg[0], seg[1])

    @staticmethod
    def _draw_ref_line(painter: QPainter, ctx: MeasurePointContext) -> None:
        if ctx.context_type != MeasureContextType.LINE:
            return
        if ctx.line_a is None or ctx.line_b is None:
            return
        pen = QPen(REF_LINE_COLOR, 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(ctx.line_a, ctx.line_b)

    def _draw_measurement(
        self,
        painter: QPainter,
        ctx_a: MeasurePointContext,
        ctx_b: MeasurePointContext,
        visible: QRectF | None = None,
    ) -> None:
        a, b = ctx_a.point, ctx_b.point
        draw_screen_dot(painter, a, self.DOT_RADIUS, QColor(46, 204, 113))
        draw_screen_dot(painter, b, self.DOT_RADIUS, QColor(230, 126, 34))

        if self._both_on_lines(ctx_a, ctx_b):
            la1, lb1 = ctx_a.line_a, ctx_a.line_b
            la2, lb2 = ctx_b.line_a, ctx_b.line_b
            assert la1 is not None and lb1 is not None and la2 is not None and lb2 is not None
            self._draw_ref_line(painter, ctx_a)
            self._draw_ref_line(painter, ctx_b)

            if lines_collinear(la1, lb1, la2, lb2):
                if (
                    perpendicular_distance(a, la1, lb1) < ALIGN_TOL
                    and perpendicular_distance(b, la1, lb1) < ALIGN_TOL
                ):
                    self._draw_aligned_on_line(painter, a, b, la1, lb1)
                else:
                    self._draw_direct(painter, a, b)
            elif lines_parallel(la1, lb1, la2, lb2):
                self._draw_parallel_lines_distance(
                    painter, a, la1, lb1, b, la2, lb2
                )
            else:
                inter = line_intersection(la1, lb1, la2, lb2)
                apparent = (
                    inter is not None
                    and is_apparent_intersection(inter, la1, lb1, la2, lb2)
                )
                self._draw_angle_between_lines(
                    painter, ctx_a, ctx_b, a, b, visible, draw_extensions=apparent
                )
            return

        line_ctx = self._pick_line_context(ctx_a, ctx_b)
        if line_ctx is not None:
            la, lb = line_ctx.line_a, line_ctx.line_b
            assert la is not None and lb is not None
            self._draw_ref_line(painter, line_ctx)

            line_pt = ctx_a if line_ctx is ctx_a else ctx_b
            other = ctx_b if line_ctx is ctx_a else ctx_a
            perp_other = perpendicular_distance(other.point, la, lb)
            perp_line = perpendicular_distance(line_pt.point, la, lb)

            if perp_other < ALIGN_TOL and perp_line < ALIGN_TOL:
                self._draw_aligned_on_line(painter, a, b, la, lb)
            elif perp_other >= perp_line:
                self._draw_perpendicular_to_line(painter, other.point, la, lb)
            else:
                self._draw_perpendicular_to_line(painter, line_pt.point, la, lb)
            return

        circle_a = self._is_hole_center(ctx_a)
        circle_b = self._is_hole_center(ctx_b)

        if circle_a and circle_b:
            self._draw_axis_triangle(painter, a, b)
            return

        if (ctx_a.apparent_intersection and circle_b) or (
            ctx_b.apparent_intersection and circle_a
        ):
            self._draw_axis_triangle(painter, a, b)
            return

        circle_ctx = self._pick_circle_context(ctx_a, ctx_b)
        if circle_ctx is not None and circle_ctx.circle_center is not None:
            other = ctx_b if circle_ctx is ctx_a else ctx_a
            if not circle_ctx.snapped:
                self._draw_center_to_point(
                    painter, circle_ctx.circle_center, other.point
                )
            else:
                self._draw_axis_triangle(painter, a, b)
            return

        self._draw_axis_triangle(painter, a, b)

    @staticmethod
    def _both_on_lines(ctx_a: MeasurePointContext, ctx_b: MeasurePointContext) -> bool:
        return (
            ctx_a.context_type == MeasureContextType.LINE
            and ctx_a.line_a is not None
            and ctx_a.line_b is not None
            and ctx_b.context_type == MeasureContextType.LINE
            and ctx_b.line_a is not None
            and ctx_b.line_b is not None
        )

    @staticmethod
    def _is_hole_center(ctx: MeasurePointContext) -> bool:
        if ctx.context_type != MeasureContextType.CIRCLE:
            return False
        if ctx.circle_center is None:
            return False
        return (
            math.hypot(
                ctx.point.x() - ctx.circle_center.x(),
                ctx.point.y() - ctx.circle_center.y(),
            )
            < ALIGN_TOL
        )

    @staticmethod
    def _pick_line_context(
        ctx_a: MeasurePointContext, ctx_b: MeasurePointContext
    ) -> MeasurePointContext | None:
        if ctx_a.context_type == MeasureContextType.LINE and ctx_a.line_a is not None and ctx_a.line_b is not None:
            return ctx_a
        if ctx_b.context_type == MeasureContextType.LINE and ctx_b.line_a is not None and ctx_b.line_b is not None:
            return ctx_b
        return None

    @staticmethod
    def _pick_circle_context(
        ctx_a: MeasurePointContext, ctx_b: MeasurePointContext
    ) -> MeasurePointContext | None:
        if ctx_a.context_type == MeasureContextType.CIRCLE and ctx_a.circle_center is not None:
            return ctx_a
        if ctx_b.context_type == MeasureContextType.CIRCLE and ctx_b.circle_center is not None:
            return ctx_b
        return None

    @staticmethod
    def _other_point(
        ctx_a: MeasurePointContext,
        ctx_b: MeasurePointContext,
        ref: MeasurePointContext,
    ) -> MeasurePointContext:
        return ctx_b if ref is ctx_a else ctx_a

    def _draw_direct(self, painter: QPainter, a: QPointF, b: QPointF) -> None:
        """Прямой размер между двумя точками (одна линия)."""
        trim = self._dot_trim(painter)
        line_a, line_b = self._trim_segment(a, b, trim, trim)
        pen = QPen(QColor(231, 76, 60), 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(line_a, line_b)
        dist = math.hypot(b.x() - a.x(), b.y() - a.y())
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        draw_screen_label(
            painter, mid, format_length(dist, self.unit),
            offset=QPointF(0, -10), font_size=self.FONT_SIZE,
        )

    def _draw_center_to_point(
        self, painter: QPainter, center: QPointF, target: QPointF
    ) -> None:
        """Размер от центра окружности/дуги до другой точки."""
        trim = self._dot_trim(painter)
        line_a, line_b = self._trim_segment(center, target, trim, trim)
        pen = QPen(QColor(231, 76, 60), 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(line_a, line_b)
        dist = math.hypot(target.x() - center.x(), target.y() - center.y())
        mid = QPointF((center.x() + target.x()) / 2, (center.y() + target.y()) / 2)
        draw_screen_label(
            painter, mid, format_length(dist, self.unit),
            offset=QPointF(0, -10), font_size=self.FONT_SIZE,
        )

    def _draw_perpendicular_to_line(
        self,
        painter: QPainter,
        from_point: QPointF,
        line_a: QPointF,
        line_b: QPointF,
    ) -> None:
        """Размер перпендикулярно линии от from_point до проекции на линию."""
        foot = project_on_line(from_point, line_a, line_b)
        px = from_point.x() - foot.x()
        py = from_point.y() - foot.y()
        dist = math.hypot(px, py)
        if dist < ALIGN_TOL:
            return

        nx, ny = px / dist, py / dist

        ldx = line_b.x() - line_a.x()
        ldy = line_b.y() - line_a.y()
        llen = math.hypot(ldx, ldy)
        if llen < 1e-12:
            return
        tx, ty = ldx / llen, ldy / llen

        tick = self._scene_pixels(painter, 6)
        label_off = self._scene_pixels(painter, 10)

        pen_ext = QPen(QColor(160, 160, 160), 1.0)
        pen_dim = QPen(QColor(231, 76, 60), 1.0)
        for pen in (pen_ext, pen_dim):
            pen.setCosmetic(True)

        painter.setPen(pen_ext)
        for anchor in (foot, from_point):
            painter.drawLine(
                QPointF(anchor.x() - tx * tick, anchor.y() - ty * tick),
                QPointF(anchor.x() + tx * tick, anchor.y() + ty * tick),
            )

        painter.setPen(pen_dim)
        trim = self._dot_trim(painter)
        line_a, line_b = self._trim_segment(foot, from_point, trim, trim)
        painter.drawLine(line_a, line_b)

        mid = QPointF((foot.x() + from_point.x()) / 2, (foot.y() + from_point.y()) / 2)
        draw_screen_label(
            painter, mid, format_length(dist, self.unit),
            offset=QPointF(nx * label_off, ny * label_off), font_size=self.FONT_SIZE,
        )

    def _draw_aligned_on_line(
        self,
        painter: QPainter,
        a: QPointF,
        b: QPointF,
        line_a: QPointF,
        line_b: QPointF,
    ) -> None:
        dx, dy = line_b.x() - line_a.x(), line_b.y() - line_a.y()
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-12:
            return
        nx, ny = -dy / seg_len, dx / seg_len
        off = self._scene_pixels(painter, 12)

        a_off = QPointF(a.x() + nx * off, a.y() + ny * off)
        b_off = QPointF(b.x() + nx * off, b.y() + ny * off)

        pen_ext = QPen(QColor(160, 160, 160), 1.0)
        pen_dim = QPen(QColor(231, 76, 60), 1.0)
        for pen in (pen_ext, pen_dim):
            pen.setCosmetic(True)

        painter.setPen(pen_ext)
        painter.drawLine(a, a_off)
        painter.drawLine(b, b_off)
        painter.setPen(pen_dim)
        painter.drawLine(a_off, b_off)

        dist = math.hypot(b.x() - a.x(), b.y() - a.y())
        mid = QPointF((a_off.x() + b_off.x()) / 2, (a_off.y() + b_off.y()) / 2)
        draw_screen_label(
            painter, mid, format_length(dist, self.unit),
            offset=QPointF(nx * off * 0.8, ny * off * 0.8), font_size=self.FONT_SIZE,
        )

    def _draw_parallel_lines_distance(
        self,
        painter: QPainter,
        point_a: QPointF,
        la1: QPointF,
        lb1: QPointF,
        point_b: QPointF,
        la2: QPointF,
        lb2: QPointF,
    ) -> None:
        """Перпендикулярное расстояние между двумя параллельными линиями."""
        d_a = perpendicular_distance(point_a, la2, lb2)
        d_b = perpendicular_distance(point_b, la1, lb1)
        if d_a <= d_b:
            self._draw_perpendicular_to_line(painter, point_a, la2, lb2)
        else:
            self._draw_perpendicular_to_line(painter, point_b, la1, lb1)

    def _draw_angle_extensions(
        self,
        painter: QPainter,
        inter: QPointF,
        la1: QPointF,
        lb1: QPointF,
        la2: QPointF,
        lb2: QPointF,
        point_a: QPointF,
        point_b: QPointF,
        along_lines: bool,
    ) -> None:
        pen = QPen(QColor(160, 160, 160), 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)

        if along_lines:
            for la, lb, pick in ((la1, lb1, point_a), (la2, lb2, point_b)):
                seg = extension_on_line_toward_inter(inter, la, lb, pick)
                if seg is not None:
                    painter.drawLine(seg[0], seg[1])
            return

        foot1 = clip_to_segment(project_on_line(point_a, la1, lb1), la1, lb1)
        foot2 = clip_to_segment(project_on_line(point_b, la2, lb2), la2, lb2)
        painter.drawLine(inter, foot1)
        painter.drawLine(inter, foot2)

    def _draw_angle_between_lines(
        self,
        painter: QPainter,
        ctx_a: MeasurePointContext,
        ctx_b: MeasurePointContext,
        point_a: QPointF,
        point_b: QPointF,
        visible: QRectF | None = None,
        draw_extensions: bool = False,
    ) -> None:
        la1, lb1 = ctx_a.line_a, ctx_a.line_b
        la2, lb2 = ctx_b.line_a, ctx_b.line_b
        assert la1 is not None and lb1 is not None and la2 is not None and lb2 is not None

        inter = line_intersection(la1, lb1, la2, lb2)
        if inter is None:
            self._draw_direct(painter, point_a, point_b)
            return

        ang_a = ray_angle_at_intersection(inter, point_a, la1, lb1)
        ang_b = ray_angle_at_intersection(inter, point_b, la2, lb2)
        start, span, angle_deg = angle_between_rays(ang_a, ang_b)
        if span < 1e-6:
            self._draw_direct(painter, point_a, point_b)
            return

        inter_offscreen = (
            visible is not None
            and not visible.isEmpty()
            and not visible.contains(inter)
        )
        along_lines = inter_offscreen or is_apparent_intersection(
            inter, la1, lb1, la2, lb2
        )

        if draw_extensions or along_lines:
            self._draw_angle_extensions(
                painter,
                inter,
                la1,
                lb1,
                la2,
                lb2,
                point_a,
                point_b,
                along_lines,
            )

        arc_r = self._arc_radius_to_picks(
            inter, point_a, la1, lb1, point_b, la2, lb2
        )
        arc_r = max(arc_r, self._scene_pixels(painter, 8))

        pen_ray = QPen(QColor(160, 160, 160), 1.0)
        pen_arc = QPen(QColor(241, 196, 15), 1.5)
        for pen in (pen_ray, pen_arc):
            pen.setCosmetic(True)

        def point_on_arc(angle: float) -> QPointF:
            return QPointF(
                inter.x() + math.cos(angle) * arc_r,
                inter.y() + math.sin(angle) * arc_r,
            )

        end_a = point_on_arc(start)
        end_b = point_on_arc(start + span)

        painter.setPen(pen_ray)
        painter.drawLine(inter, end_a)
        painter.drawLine(inter, end_b)

        rect = QRectF(inter.x() - arc_r, inter.y() - arc_r, arc_r * 2, arc_r * 2)
        painter.setPen(pen_arc)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            rect,
            int(-math.degrees(start) * 16),
            int(-math.degrees(span) * 16),
        )

        mid_ang = start + span / 2
        label_pos = QPointF(
            inter.x() + math.cos(mid_ang) * (arc_r + self._scene_pixels(painter, 14)),
            inter.y() + math.sin(mid_ang) * (arc_r + self._scene_pixels(painter, 14)),
        )
        if inter_offscreen:
            label_pos = QPointF(
                (end_a.x() + end_b.x()) / 2,
                (end_a.y() + end_b.y()) / 2,
            )
        label_pos = self._clamp_to_visible(label_pos, visible, painter)
        draw_screen_label(
            painter,
            label_pos,
            f"{angle_deg:.1f}°",
            offset=QPointF(0, -10),
            font_size=self.FONT_SIZE,
        )

    def _draw_axis_triangle(self, painter: QPainter, a: QPointF, b: QPointF) -> None:
        dx = abs(b.x() - a.x())
        dy = abs(b.y() - a.y())
        diag = math.hypot(dx, dy)
        horizontal = dy < ALIGN_TOL
        vertical = dx < ALIGN_TOL

        pen_h = QPen(QColor(46, 204, 113), 1.0)
        pen_v = QPen(QColor(52, 152, 219), 1.0)
        pen_d = QPen(QColor(231, 76, 60), 1.0)
        for pen in (pen_h, pen_v, pen_d):
            pen.setCosmetic(True)

        placed: list[QRectF] = []

        if horizontal:
            painter.setPen(pen_h)
            painter.drawLine(a, b)
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            rect = draw_screen_label(
                painter, mid, format_length(dx, self.unit),
                offset=QPointF(0, -10), font_size=self.FONT_SIZE, placed_rects=placed,
            )
            if rect:
                placed.append(rect)
        elif vertical:
            painter.setPen(pen_v)
            painter.drawLine(a, b)
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            rect = draw_screen_label(
                painter, mid, format_length(dy, self.unit),
                offset=QPointF(12, 0), font_size=self.FONT_SIZE, placed_rects=placed,
            )
            if rect:
                placed.append(rect)
        else:
            corner = QPointF(b.x(), a.y())
            painter.setPen(pen_h)
            painter.drawLine(a, corner)
            painter.setPen(pen_v)
            painter.drawLine(corner, b)
            painter.setPen(pen_d)
            painter.drawLine(a, b)

            mid_h = QPointF((a.x() + corner.x()) / 2, a.y())
            mid_v = QPointF(b.x(), (corner.y() + b.y()) / 2)
            mid_d = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)

            for mid, text, off in (
                (mid_h, format_length(dx, self.unit), QPointF(0, -10)),
                (mid_v, format_length(dy, self.unit), QPointF(12, 0)),
                (mid_d, format_length(diag, self.unit), QPointF(0, -14)),
            ):
                rect = draw_screen_label(
                    painter, mid, text, offset=off,
                    font_size=self.FONT_SIZE, placed_rects=placed,
                )
                if rect:
                    placed.append(rect)
