"""Простой пространственный индекс для ускорения привязок и выбора."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF

from skyview.dxf.loader import EntityRecord


class RecordSpatialIndex:
    """Равномерная сетка по bounds записей."""

    __slots__ = ("_cell", "_buckets")

    def __init__(self, cell_size: float) -> None:
        self._cell = max(cell_size, 1e-6)
        self._buckets: dict[tuple[int, int], list[EntityRecord]] = {}

    @classmethod
    def build(cls, records: list[EntityRecord]) -> RecordSpatialIndex | None:
        if len(records) < 800:
            return None
        extents = _records_extents(records)
        if extents is None:
            return None
        xmin, ymin, xmax, ymax = extents
        span = max(xmax - xmin, ymax - ymin, 1.0)
        cell = span / max(32, min(256, int(math.sqrt(len(records)))))
        index = cls(cell)
        for record in records:
            bounds = record.bounds
            if bounds.isNull():
                index._insert((0, 0), record)
                continue
            x0 = int(math.floor(bounds.left() / cell))
            y0 = int(math.floor(bounds.top() / cell))
            x1 = int(math.floor(bounds.right() / cell))
            y1 = int(math.floor(bounds.bottom() / cell))
            seen: set[tuple[int, int]] = set()
            for xi in range(x0, x1 + 1):
                for yi in range(y0, y1 + 1):
                    key = (xi, yi)
                    if key in seen:
                        continue
                    seen.add(key)
                    index._insert(key, record)
        return index

    def _insert(self, key: tuple[int, int], record: EntityRecord) -> None:
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = [record]
        else:
            bucket.append(record)

    def query_rect(self, rect: QRectF) -> list[EntityRecord]:
        if rect.isEmpty():
            return []
        x0 = int(math.floor(rect.left() / self._cell))
        y0 = int(math.floor(rect.top() / self._cell))
        x1 = int(math.floor(rect.right() / self._cell))
        y1 = int(math.floor(rect.bottom() / self._cell))
        result: list[EntityRecord] = []
        seen: set[str] = set()
        for xi in range(x0, x1 + 1):
            for yi in range(y0, y1 + 1):
                for record in self._buckets.get((xi, yi), ()):
                    handle = record.handle
                    if handle in seen:
                        continue
                    if record.bounds.isNull() or record.bounds.intersects(rect):
                        seen.add(handle)
                        result.append(record)
        return result


def _records_extents(records: list[EntityRecord]) -> tuple[float, float, float, float] | None:
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    for record in records:
        bounds = record.bounds
        if bounds.isNull():
            continue
        xmin = min(xmin, bounds.left())
        ymin = min(ymin, bounds.top())
        xmax = max(xmax, bounds.right())
        ymax = max(ymax, bounds.bottom())
    if xmin == float("inf"):
        return None
    return xmin, ymin, xmax, ymax
