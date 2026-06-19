"""Проекции габарита чертежа по краям холста."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from skyview.dxf.units import format_length
from skyview.ui.theme import overlay_line_color, overlay_text_color


class BoundsOverlayWidget(QWidget):
    MARGIN = 10
    TICK = 5

    def __init__(self, parent=None, dark: bool = True):
        super().__init__(parent)
        self._dark = dark
        self._visible = False
        self._width = 0.0
        self._height = 0.0
        self._unit = "mm"
        self._proj = QRectF()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_dark_mode(self, dark: bool) -> None:
        self._dark = dark
        self.update()

    def set_state(
        self,
        visible: bool,
        width: float,
        height: float,
        unit: str,
        proj: QRectF,
    ) -> None:
        self._visible = visible and not proj.isEmpty() and width > 0 and height > 0
        self._width = width
        self._height = height
        self._unit = unit
        self._proj = proj
        self.setVisible(self._visible)
        self.update()

    def paintEvent(self, event) -> None:
        if not self._visible:
            return

        x1 = self._proj.left()
        x2 = self._proj.right()
        y1 = self._proj.top()
        y2 = self._proj.bottom()
        y_top = self.MARGIN + self.TICK
        x_left = self.MARGIN + self.TICK

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(overlay_line_color(self._dark), 2)
        p.setPen(pen)

        p.drawLine(int(x1), int(y_top), int(x2), int(y_top))
        p.drawLine(int(x1), int(y_top), int(x1), int(y_top + self.TICK))
        p.drawLine(int(x2), int(y_top), int(x2), int(y_top + self.TICK))

        p.drawLine(int(x_left), int(y1), int(x_left), int(y2))
        p.drawLine(int(x_left), int(y1), int(x_left + self.TICK), int(y1))
        p.drawLine(int(x_left), int(y2), int(x_left + self.TICK), int(y2))

        font = QFont("Segoe UI", 9)
        p.setFont(font)
        p.setPen(overlay_text_color(self._dark))

        w_label = format_length(self._width, self._unit)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(w_label)
        p.drawText(int((x1 + x2 - tw) / 2), int(self.MARGIN), w_label)

        h_label = format_length(self._height, self._unit)
        th = fm.horizontalAdvance(h_label)
        cy = (y1 + y2) / 2
        p.save()
        p.translate(int(self.MARGIN - 2), int(cy + th / 2))
        p.rotate(-90)
        p.drawText(0, 0, h_label)
        p.restore()
        p.end()
