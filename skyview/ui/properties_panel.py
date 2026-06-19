"""Панель свойств выбранного объекта."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skyview.dxf.units import format_length


PROP_LABELS: dict[str, str] = {
    "type": "Тип",
    "layer": "Слой",
    "handle": "Handle",
    "length": "Длина",
    "radius": "Радиус",
    "diameter": "Диаметр",
    "center": "Центр",
    "start": "Начало",
    "end": "Конец",
    "start_angle": "Начальный угол",
    "end_angle": "Конечный угол",
    "arc_length": "Длина дуги",
    "major_axis": "Большая ось",
    "minor_axis": "Малая ось",
    "vertex_count": "Вершин",
    "closed": "Замкнутый",
    "location": "Положение",
    "text": "Текст",
    "height": "Высота",
    "char_height": "Высота символа",
    "insert": "Точка вставки",
    "degree": "Степень",
    "control_points": "Контрольных точек",
}


class PropertiesPanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("propertiesPanel")
        self._unit = "mm"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Свойства объекта")
        title.setObjectName("panelTitle")
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #a6adc8;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._count_label)
        layout.addLayout(header)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Свойство", "Значение"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self._table)

    def set_unit(self, unit: str) -> None:
        self._unit = unit

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._count_label.setText("")

    def show_empty(self) -> None:
        self.clear()
        self._count_label.setText("Ничего не выбрано")

    def show_bounding_size(self, width: float, height: float) -> None:
        self._table.setRowCount(0)
        self._count_label.setText("Габарит чертежа")
        rows = [
            ("Ширина", format_length(width, self._unit)),
            ("Высота", format_length(height, self._unit)),
        ]
        self._table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(label))
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(i, 1, item)

    def show_properties(self, records: list[dict[str, Any]]) -> None:
        self._table.setRowCount(0)
        if not records:
            self._count_label.setText("Ничего не выбрано")
            return

        if len(records) == 1:
            self._count_label.setText("")
            props = records[0]
        else:
            self._count_label.setText(f"Выбрано: {len(records)}")
            # Общие свойства для множественного выбора
            props = {"type": ", ".join(sorted({r.get("type", "") for r in records}))}
            layers = {r.get("layer", "") for r in records}
            if len(layers) == 1:
                props["layer"] = layers.pop()

        rows = []
        for key, value in props.items():
            label = PROP_LABELS.get(key, key)
            rows.append((label, self._format_value(key, value)))

        self._table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(label))
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(i, 1, item)

    def _format_value(self, key: str, value: Any) -> str:
        if value is None:
            return "—"
        if key in ("length", "radius", "diameter", "arc_length", "major_axis", "minor_axis", "height", "char_height"):
            if isinstance(value, (int, float)):
                return format_length(float(value), self._unit)
        if isinstance(value, bool):
            return "Да" if value else "Нет"
        if isinstance(value, tuple) and len(value) == 2:
            return f"({value[0]:.3f}, {value[1]:.3f})"
        return str(value)
