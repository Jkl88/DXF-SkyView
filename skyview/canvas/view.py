"""Холст DXF — сцена и вид."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from skyview.canvas.items import DxfPathItem, SnapMarkerItem
from skyview.cad_files import is_cad_file
from skyview.dxf.bounds import records_scene_bounds, records_size
from skyview.dxf.loader import DxfDocument, EntityRecord
from skyview.tools.measure import MeasureOverlay
from skyview.tools.measure_context import (
    MeasureContextType,
    circle_center_for_handle,
    is_valid_measure_point,
    resolve_measure_point,
)
from skyview.tools.snap import SNAP_LABELS, SnapEngine, SnapMode, SnapSettings
from skyview.tools.undo import UndoStack
from skyview.ui.bounds_overlay import BoundsOverlayWidget
from skyview.ui.scale_bar import ScaleBarWidget
from skyview.ui.theme import canvas_background


class DxfScene(QGraphicsScene):
    def __init__(self, dark: bool = True):
        super().__init__()
        self._dark = dark
        self.setBackgroundBrush(canvas_background(dark))
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self._items: list[DxfPathItem] = []
        self._selected: set[DxfPathItem] = set()
        self._snap_highlighted: list[DxfPathItem] = []
        self._records_cache: list[EntityRecord] | None = None

    def clear_all(self) -> None:
        for item in list(self._items):
            self.removeItem(item)
        self._items.clear()
        self._selected.clear()
        self._snap_highlighted.clear()
        self._records_cache = None

    def item_by_handle(self, handle: str) -> DxfPathItem | None:
        for item in self._items:
            if item.record.handle == handle:
                return item
        return None

    def set_snap_highlight(
        self, handle: str | list[str] | None, kind: str | None = None
    ) -> None:
        for item in self._snap_highlighted:
            item.set_snap_highlight(None)
        self._snap_highlighted.clear()
        if handle is None:
            return
        handles = [handle] if isinstance(handle, str) else list(handle)
        seen: set[str] = set()
        for h in handles:
            if h in seen:
                continue
            seen.add(h)
            item = self.item_by_handle(h)
            if item is None:
                continue
            item.set_snap_highlight(kind)
            self._snap_highlighted.append(item)

    def add_records(self, records) -> list[DxfPathItem]:
        items = []
        for rec in records:
            item = DxfPathItem(rec, dark=self._dark)
            self.addItem(item)
            items.append(item)
        self._items = items
        self._records_cache = None
        if items:
            depth = int(max(6, min(12, math.log2(len(items) + 1) + 4)))
            self.setBspTreeDepth(depth)
        return items

    def restore_records(self, records: list[EntityRecord]) -> list[DxfPathItem]:
        restored = []
        for rec in records:
            item = DxfPathItem(rec, dark=self._dark)
            self.addItem(item)
            self._items.append(item)
            restored.append(item)
        self._records_cache = None
        return restored

    def set_dark_mode(self, dark: bool) -> None:
        self._dark = dark
        self.setBackgroundBrush(canvas_background(dark))
        for item in self._items:
            item.set_dark_mode(dark)

    def all_records(self) -> list[EntityRecord]:
        if self._records_cache is None:
            self._records_cache = [item.record for item in self._items]
        return self._records_cache

    def content_bounding_rect(self) -> QRectF:
        return records_scene_bounds([item.record for item in self._items])

    def all_items(self) -> list[DxfPathItem]:
        return list(self._items)

    def select_item(self, item: DxfPathItem, additive: bool = False) -> None:
        if not additive:
            for sel in list(self._selected):
                sel.set_highlight(False)
            self._selected.clear()
        if item in self._selected:
            item.set_highlight(False)
            self._selected.discard(item)
        else:
            item.set_highlight(True)
            self._selected.add(item)

    def clear_selection(self) -> None:
        for sel in self._selected:
            sel.set_highlight(False)
        self._selected.clear()

    def selected_items(self) -> list[DxfPathItem]:
        return list(self._selected)

    def remove_selected(self) -> list[EntityRecord]:
        removed: list[EntityRecord] = []
        for item in list(self._selected):
            removed.append(item.record)
            self.removeItem(item)
            self._items.remove(item)
        self._selected.clear()
        self._records_cache = None
        return removed

    def items_at(self, scene_pos: QPointF, tol: float = 4.0) -> list[DxfPathItem]:
        rect = QRectF(
            scene_pos.x() - tol,
            scene_pos.y() - tol,
            tol * 2,
            tol * 2,
        )
        candidates = [
            item
            for item in self.items(
                rect,
                Qt.ItemSelectionMode.IntersectsItemBoundingRect,
                Qt.SortOrder.DescendingOrder,
            )
            if isinstance(item, DxfPathItem)
        ]
        hits: list[tuple[float, float, DxfPathItem]] = []
        for item in candidates:
            dist = item.pick_distance(scene_pos)
            if dist is None or dist > tol:
                continue
            area = item.boundingRect().width() * item.boundingRect().height()
            hits.append((dist, area, item))
        hits.sort(key=lambda entry: (entry[0], entry[1]))
        return [item for _dist, _area, item in hits]


class DxfCanvas(QGraphicsView):
    selection_changed = Signal(list)
    snap_info = Signal(str)
    cursor_moved = Signal(float, float)
    document_modified = Signal()
    file_dropped = Signal(str)
    measure_exit_requested = Signal()

    def __init__(self, snap_settings: SnapSettings, dark: bool = True, parent=None):
        super().__init__(parent)
        self._dark = dark
        self._snap_settings = snap_settings
        self._snap_engine = SnapEngine(snap_settings)
        self._undo = UndoStack()
        self._doc: DxfDocument | None = None
        self._tool = "select"  # select | measure
        self._measure: MeasureOverlay | None = None
        self._snap_marker = SnapMarkerItem(dark)
        self._last_snap_result = None

        self._scene = DxfScene(dark)
        self.setScene(self._scene)
        self._scene.addItem(self._snap_marker)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)

        self._scale_bar = ScaleBarWidget(self.viewport(), dark=self._dark)
        self._bounds_overlay = BoundsOverlayWidget(self.viewport(), dark=self._dark)
        self._bounds_overlay.raise_()
        self._scale_bar.raise_()

        self._panning = False
        self._pan_start = QPointF()

    @property
    def document(self) -> DxfDocument | None:
        return self._doc

    @property
    def tool(self) -> str:
        return self._tool

    def load_document(self, doc: DxfDocument) -> None:
        self._doc = doc
        self._undo.clear()
        self._scene.clear_all()
        self._scene.add_records(doc.records)
        self._snap_engine.set_records(doc.records)

        if self._measure is None:
            self._measure = MeasureOverlay(doc.unit_short)
            self._scene.addItem(self._measure)
        else:
            self._measure.set_unit(doc.unit_short)
            self._measure.reset()

        self.fit_to_view()
        self._update_viewport_overlays()
        self._scene.clear_selection()
        self.selection_changed.emit([])

    def content_size(self) -> tuple[float, float]:
        return records_size([item.record for item in self._scene.all_items()])

    def has_selection(self) -> bool:
        return bool(self._scene.selected_items())

    def selected_records(self) -> list:
        return [item.record for item in self._scene.selected_items()]

    def remaining_records(self) -> list:
        return [item.record for item in self._scene.all_items()]

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        if self._measure:
            self._measure.reset()

    def update_snap_settings(self, settings: SnapSettings | None = None) -> None:
        if settings is not None:
            self._snap_settings = settings
        self._snap_engine.settings = self._snap_settings

    def set_dark_mode(self, dark: bool) -> None:
        if self._dark == dark:
            return
        self._dark = dark
        self._scene.set_dark_mode(dark)
        self._snap_marker.set_dark_mode(dark)
        self._scale_bar.set_dark_mode(dark)
        self._bounds_overlay.set_dark_mode(dark)
        self.viewport().update()

    def fit_to_view(self) -> None:
        rect = self._scene.content_bounding_rect()
        if rect.isEmpty():
            return
        self.resetTransform()
        margin = max(rect.width(), rect.height()) * 0.01 + 1
        self.fitInView(
            rect.adjusted(-margin, -margin, margin, margin),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._update_viewport_overlays()

    def _scale_factor(self) -> float:
        return abs(self.transform().m11()) or 1.0

    def _update_viewport_overlays(self) -> None:
        unit = self._doc.unit_short if self._doc else ""
        self._scale_bar.set_scale(self._scale_factor(), unit)
        self._position_scale_bar()
        self._position_bounds_overlay()
        self._update_bounds_overlay()

    def _bbox_in_viewport(self) -> QRectF:
        rect = self._scene.content_bounding_rect()
        if rect.isEmpty():
            return QRectF()
        tl = self.mapFromScene(rect.topLeft())
        br = self.mapFromScene(rect.bottomRight())
        vp = self.viewport()
        x1 = tl.x() - vp.x()
        y1 = tl.y() - vp.y()
        x2 = br.x() - vp.x()
        y2 = br.y() - vp.y()
        return QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized()

    def _update_bounds_overlay(self) -> None:
        width, height = self.content_size()
        show = not self._scene.selected_items()
        self._bounds_overlay.set_state(
            show,
            width,
            height,
            self._doc.unit_short if self._doc else "",
            self._bbox_in_viewport(),
        )

    def _position_scale_bar(self) -> None:
        vp = self.viewport()
        w = vp.width()
        h = vp.height()
        bw = self._scale_bar.sizeHint().width()
        self._scale_bar.setGeometry(w - bw - 4, h - self._scale_bar.height() - 4, bw, self._scale_bar.height())

    def _position_bounds_overlay(self) -> None:
        vp = self.viewport()
        self._bounds_overlay.setGeometry(0, 0, vp.width(), vp.height())

    def _scene_pos(self, event) -> QPointF:
        return self.mapToScene(event.position().toPoint())

    def _visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def _resolve_point(self, scene_pos: QPointF) -> tuple[QPointF, object]:
        snap = self._snap_engine.snap(
            scene_pos, self._scale_factor(), self._visible_scene_rect()
        )
        self._last_snap_result = snap
        records = self._scene.all_records()

        measure_ctx = None
        if self._tool == "measure":
            measure_ctx = resolve_measure_point(
                scene_pos,
                records,
                snap,
                self._scale_factor(),
                self._snap_settings,
            )

        center_enabled = self._snap_settings.is_enabled(SnapMode.CENTER)
        center_handle: str | None = None
        if snap and snap.mode == SnapMode.CENTER and snap.ref_handle:
            center_handle = snap.ref_handle
        elif (
            snap
            and snap.mode == SnapMode.RADIAL
            and snap.ref_handle
            and center_enabled
        ):
            center_handle = snap.ref_handle
        elif (
            center_enabled
            and measure_ctx
            and measure_ctx.context_type == MeasureContextType.CIRCLE
            and measure_ctx.circle_handle
        ):
            center_handle = measure_ctx.circle_handle

        if snap and snap.mode == SnapMode.QUADRANT and snap.ref_handle:
            self._scene.set_snap_highlight(snap.ref_handle, "quadrant")
        elif snap and snap.mode == SnapMode.INTERSECTION:
            handles = [
                h
                for h in (snap.ref_handle, snap.ref_handle2)
                if h
            ]
            self._scene.set_snap_highlight(handles or None, "intersection")
        elif center_handle:
            self._scene.set_snap_highlight(center_handle, "center")
        elif snap and snap.mode == SnapMode.LINE and snap.ref_handle:
            self._scene.set_snap_highlight(snap.ref_handle, "line")
        elif snap and snap.mode == SnapMode.MIDPOINT and snap.ref_handle:
            self._scene.set_snap_highlight(snap.ref_handle, "midpoint")
        elif (
            self._snap_settings.is_enabled(SnapMode.LINE)
            and measure_ctx
            and measure_ctx.context_type == MeasureContextType.LINE
            and measure_ctx.line_handle
            and snap is None
        ):
            self._scene.set_snap_highlight(measure_ctx.line_handle, "line")
        else:
            self._scene.set_snap_highlight(None)

        marker_point: QPointF | None = None
        if snap:
            if (
                snap.mode == SnapMode.CENTER
                or (snap.mode == SnapMode.RADIAL and center_enabled)
            ) and snap.ref_handle:
                hit = circle_center_for_handle(records, snap.ref_handle)
                marker_point = hit[0] if hit else snap.point
            else:
                marker_point = snap.point
        elif (
            center_enabled
            and measure_ctx
            and measure_ctx.context_type == MeasureContextType.CIRCLE
        ):
            marker_point = measure_ctx.point

        if marker_point is not None:
            self._snap_marker.show_at(marker_point.x(), marker_point.y())
            if (
                snap
                and snap.mode == SnapMode.APPARENT_INTERSECTION
                and snap.ref_line_a is not None
                and snap.ref_line_b is not None
                and snap.ref_line2_a is not None
                and snap.ref_line2_b is not None
            ):
                self._snap_marker.set_apparent_guides(
                    snap.point,
                    snap.ref_line_a,
                    snap.ref_line_b,
                    snap.ref_line2_a,
                    snap.ref_line2_b,
                )
            else:
                self._snap_marker.clear_apparent_guides()
        else:
            self._snap_marker.hide_marker()

        if self._tool == "measure":
            ctx = measure_ctx
            assert ctx is not None
            if snap and snap.mode == SnapMode.CENTER:
                self.snap_info.emit("Привязка: Центр")
            elif snap and snap.mode == SnapMode.RADIAL and center_enabled:
                self.snap_info.emit("Привязка: Центр")
            elif snap:
                self.snap_info.emit(f"Привязка: {SNAP_LABELS[snap.mode]}")
            elif center_enabled and ctx.context_type == MeasureContextType.CIRCLE:
                self.snap_info.emit("Привязка: Центр")
            elif (
                self._snap_settings.is_enabled(SnapMode.LINE)
                and ctx.context_type == MeasureContextType.LINE
            ):
                self.snap_info.emit("Привязка: Линия")
            else:
                self.snap_info.emit("")
            return ctx.point, ctx

        if snap and snap.mode == SnapMode.CENTER:
            self.snap_info.emit("Привязка: Центр")
            hit = circle_center_for_handle(records, snap.ref_handle)
            if hit:
                return hit[0], snap
            return snap.point, snap

        if snap and snap.mode == SnapMode.RADIAL and center_enabled:
            self.snap_info.emit("Привязка: Центр")
            hit = circle_center_for_handle(records, snap.ref_handle)
            if hit:
                return hit[0], snap
            return snap.point, snap

        if snap:
            self.snap_info.emit(f"Привязка: {SNAP_LABELS[snap.mode]}")
        else:
            self.snap_info.emit("")

        if snap:
            return snap.point, snap
        return scene_pos, None

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        self._update_viewport_overlays()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            if self._tool == "measure":
                self.measure_exit_requested.emit()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        scene_pos = self._scene_pos(event)
        pos, ctx = self._resolve_point(scene_pos)
        self.cursor_moved.emit(pos.x(), -pos.y())

        if self._tool == "measure" and self._measure:
            phase = self._measure.state.phase
            if not is_valid_measure_point(ctx):
                event.accept()
                return
            if phase == 0:
                self._measure.set_point_a(ctx)
            elif phase == 1:
                self._measure.set_point_b(ctx)
            event.accept()
            return

        if self._tool == "select":
            additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            scale = self._scale_factor()
            pick_tol = max(8.0 / scale, 3.0)
            hits = self._scene.items_at(scene_pos, pick_tol)
            if hits:
                self._scene.select_item(hits[0], additive=additive)
            elif not additive:
                self._scene.clear_selection()
            self._emit_selection()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            self._update_viewport_overlays()
            event.accept()
            return

        pos, ctx = self._resolve_point(self._scene_pos(event))
        self.cursor_moved.emit(pos.x(), -pos.y())

        if self._tool == "measure" and self._measure:
            if is_valid_measure_point(ctx):
                self._measure.set_cursor(ctx)
            else:
                self._measure.set_cursor(None)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _emit_selection(self) -> None:
        records = [item.record for item in self._scene.selected_items()]
        self._update_bounds_overlay()
        self.selection_changed.emit(records)

    def delete_selected(self) -> int:
        removed = self._scene.remove_selected()
        if removed:
            self._undo.push_delete(removed)
            remaining = [item.record for item in self._scene.all_items()]
            self._snap_engine.set_records(remaining)
            self._emit_selection()
            self.document_modified.emit()
        return len(removed)

    def undo_delete(self) -> int:
        action = self._undo.pop_undo()
        if not action:
            return 0
        self._scene.restore_records(action.records)
        remaining = [item.record for item in self._scene.all_items()]
        self._snap_engine.set_records(remaining)
        self._emit_selection()
        self.document_modified.emit()
        return len(action.records)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_viewport_overlays()

    @staticmethod
    def _cad_from_mime(mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if is_cad_file(path):
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._cad_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._cad_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._cad_from_mime(event.mimeData())
        if path:
            self.file_dropped.emit(path)
            event.acceptProposedAction()
        else:
            event.ignore()
