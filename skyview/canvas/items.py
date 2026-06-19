"""Графические элементы сцены."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from skyview.canvas.screen_overlay import draw_screen_diamond
from skyview.dxf.loader import EntityRecord, make_pen

_OUTLINE_ONLY_TYPES = frozenset({"LWPOLYLINE", "POLYLINE"})


class DxfPathItem(QGraphicsPathItem):
    """Элемент чертежа с привязкой к записи DXF."""

    TYPE = "dxf_entity"

    def __init__(self, record: EntityRecord):
        super().__init__(record.path)
        self.record = record
        self._selected = False
        self._snap_highlight: str | None = None
        self._base_color = record.color
        self.setPen(make_pen(self._base_color, 1.0))
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setData(0, self.TYPE)
        self.setData(1, record.handle)

    def set_highlight(self, on: bool) -> None:
        self._selected = on
        self._apply_pen()
        self.update()

    def set_snap_highlight(self, kind: str | None) -> None:
        self._snap_highlight = kind
        self._apply_pen()
        self.update()

    def _apply_pen(self) -> None:
        if self._snap_highlight == "center":
            self.setPen(make_pen(QColor(46, 204, 113), 2.0))
        elif self._snap_highlight == "line":
            self.setPen(make_pen(QColor(100, 180, 255), 2.0))
        elif self._snap_highlight in ("quadrant", "intersection", "midpoint") or self._selected:
            self.setPen(make_pen(QColor(255, 220, 0), 2.0))
        else:
            self.setPen(make_pen(self._base_color, 1.0))

    def is_highlighted(self) -> bool:
        return self._selected

    def _outline_only(self) -> bool:
        return self.record.entity_type in _OUTLINE_ONLY_TYPES

    def _stroke_hit_shape(self, tol: float):
        stroker = QPainterPathStroker()
        pen = self.pen()
        stroker.setWidth(max(pen.widthF(), tol * 2))
        stroker.setCapStyle(pen.capStyle())
        stroker.setJoinStyle(pen.joinStyle())
        return stroker.createStroke(self.path())

    def matches_click(self, scene_pos: QPointF, tol: float) -> bool:
        if self._outline_only():
            return self._stroke_hit_shape(tol).contains(scene_pos)
        return self.shape().contains(scene_pos)

    def shape(self):
        if self._outline_only():
            return self._stroke_hit_shape(4.0)
        return super().shape()

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self._selected:
            from skyview.tools.snap import _entity_centers, _entity_endpoints

            pts = _entity_endpoints(self.record)
            if not pts:
                pts = _entity_centers(self.record)
            for pt in pts:
                draw_screen_diamond(painter, pt, size=4.0)


class SnapMarkerItem(QGraphicsItem):
    """Маркер активной привязки — фиксированный жёлтый ромб."""

    def __init__(self):
        super().__init__()
        self.setZValue(999)
        self.setVisible(False)
        self._scene_pos = None
        self._apparent_inter: QPointF | None = None
        self._apparent_lines: tuple[QPointF, QPointF, QPointF, QPointF] | None = None

    def show_at(self, x: float, y: float) -> None:
        from PySide6.QtCore import QPointF

        self._scene_pos = QPointF(x, y)
        self.setVisible(True)
        self.update()

    def set_apparent_guides(
        self,
        inter,
        la1,
        lb1,
        la2,
        lb2,
    ) -> None:
        self._apparent_inter = inter
        self._apparent_lines = (la1, lb1, la2, lb2)
        self.update()

    def clear_apparent_guides(self) -> None:
        self._apparent_inter = None
        self._apparent_lines = None
        self.update()

    def hide_marker(self) -> None:
        self._scene_pos = None
        self._apparent_inter = None
        self._apparent_lines = None
        self.setVisible(False)
        self.update()

    def boundingRect(self):
        from PySide6.QtCore import QRectF

        return QRectF(-1e6, -1e6, 2e6, 2e6)

    def paint(self, painter, option, widget=None) -> None:
        if self._apparent_inter is not None and self._apparent_lines is not None:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QColor, QPen

            from skyview.tools.measure_context import apparent_guide_segment

            la1, lb1, la2, lb2 = self._apparent_lines
            pen = QPen(QColor(210, 210, 210, 220), 1.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for la, lb in ((la1, lb1), (la2, lb2)):
                seg = apparent_guide_segment(self._apparent_inter, la, lb)
                if seg is not None:
                    painter.drawLine(seg[0], seg[1])

        if self._scene_pos is not None:
            draw_screen_diamond(painter, self._scene_pos, size=4.0)
