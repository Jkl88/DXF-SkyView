"""Шкала масштаба в углу холста."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from skyview.dxf.units import format_length


def _nice_scale_length(raw: float) -> float:
    """Подобрать «красивую» длину шкалы, кратную 5."""
    if raw <= 0:
        return 5.0
    magnitude = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 5, 10):
        val = mult * magnitude
        if val >= raw * 0.6:
            rounded = round(val / 5) * 5
            if rounded <= 0:
                rounded = 5.0
            return float(rounded)
    return round(raw / 5) * 5 or 5.0


class ScaleBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._unit = "mm"
        self._pixels_per_unit = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(36)

    def set_scale(self, pixels_per_unit: float, unit: str) -> None:
        self._pixels_per_unit = max(pixels_per_unit, 1e-9)
        self._unit = unit
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        bar_units = _nice_scale_length(100 / self._pixels_per_unit)
        bar_px = int(bar_units * self._pixels_per_unit) + 40
        return QSize(max(bar_px, 80), 36)

    def paintEvent(self, event) -> None:
        ppu = self._pixels_per_unit
        bar_units = _nice_scale_length(100 / ppu)
        bar_px = bar_units * ppu

        w = self.width()
        h = self.height()
        margin = 12
        x0 = w - margin - bar_px
        y0 = h - 14

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(200, 200, 200), 2)
        p.setPen(pen)
        p.drawLine(int(x0), int(y0), int(x0 + bar_px), int(y0))
        p.drawLine(int(x0), int(y0 - 4), int(x0), int(y0 + 4))
        p.drawLine(int(x0 + bar_px), int(y0 - 4), int(x0 + bar_px), int(y0 + 4))

        label = format_length(bar_units, self._unit, precision=0 if bar_units >= 10 else 1)
        font = QFont("Segoe UI", 9)
        p.setFont(font)
        p.setPen(QColor(220, 220, 220))
        tw = p.fontMetrics().horizontalAdvance(label)
        p.drawText(int(x0 + (bar_px - tw) / 2), int(y0 - 6), label)
        p.end()
