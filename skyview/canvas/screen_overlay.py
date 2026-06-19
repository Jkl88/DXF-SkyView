"""Экранно-фиксированная отрисовка поверх сцены (не зависит от масштаба)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen


def scene_to_device(painter: QPainter, scene_pos: QPointF) -> QPointF:
    return painter.worldTransform().map(scene_pos)


def draw_screen_diamond(
    painter: QPainter,
    scene_pos: QPointF,
    size: float = 4.0,
    color: QColor | None = None,
) -> None:
    color = color or QColor(255, 220, 0)
    center = scene_to_device(painter, scene_pos)
    painter.save()
    painter.resetTransform()
    path = QPainterPath()
    path.moveTo(center.x(), center.y() - size)
    path.lineTo(center.x() + size, center.y())
    path.lineTo(center.x(), center.y() + size)
    path.lineTo(center.x() - size, center.y())
    path.closeSubpath()
    pen = QPen(color.darker(110), 1.0)
    painter.setPen(pen)
    painter.setBrush(QColor(color.red(), color.green(), color.blue(), 90))
    painter.drawPath(path)
    painter.restore()


def draw_screen_dot(
    painter: QPainter,
    scene_pos: QPointF,
    radius: float,
    color: QColor,
) -> None:
    center = scene_to_device(painter, scene_pos)
    painter.save()
    painter.resetTransform()
    pen = QPen(color.darker(120), 1.0)
    painter.setPen(pen)
    painter.setBrush(color)
    painter.drawEllipse(center, radius, radius)
    painter.restore()


def draw_screen_label(
    painter: QPainter,
    scene_pos: QPointF,
    text: str,
    offset: QPointF | None = None,
    font_size: int = 9,
    placed_rects: list[QRectF] | None = None,
) -> QRectF | None:
    """Нарисовать подпись в экранных координатах. Возвращает занятый прямоугольник."""
    offset = offset or QPointF(0, -10)
    center = scene_to_device(painter, scene_pos)
    painter.save()
    painter.resetTransform()

    font = QFont("Segoe UI", font_size)
    painter.setFont(font)
    fm = painter.fontMetrics()
    w = fm.horizontalAdvance(text) + 6
    h = fm.height() + 2

    candidates = [
        offset,
        QPointF(0, -h - 6),
        QPointF(0, h + 6),
        QPointF(w / 2 + 4, 0),
        QPointF(-w / 2 - 4, 0),
        QPointF(w / 2 + 4, -h),
        QPointF(-w / 2 - 4, -h),
    ]

    chosen = candidates[0]
    if placed_rects is not None:
        for cand in candidates:
            rect = QRectF(
                center.x() + cand.x() - w / 2,
                center.y() + cand.y() - h / 2,
                w,
                h,
            )
            if not any(rect.intersects(r) for r in placed_rects):
                chosen = cand
                break

    rect = QRectF(
        center.x() + chosen.x() - w / 2,
        center.y() + chosen.y() - h / 2,
        w,
        h,
    )
    painter.fillRect(rect, QColor(30, 30, 30, 210))
    painter.setPen(QColor(240, 240, 240))
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
    painter.restore()
    return rect
