"""Панель свойств выбранного объекта."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skyview.dxf.units import format_length, parse_length

_ROLE_KEY = Qt.ItemDataRole.UserRole
_ROLE_FORMATTED = Qt.ItemDataRole.UserRole + 1

_EDITABLE_CIRCULAR = frozenset({"radius", "diameter"})
_SIMILAR_TYPES = frozenset({"LINE", "CIRCLE", "ARC"})
_UNIQUE_KEYS = frozenset({"handle", "center", "start", "end", "location", "insert"})
_FLOAT_TOL = 1e-6

PROP_LABELS: dict[str, str] = {
    "type": "Тип",
    "layer": "Слой",
    "handle": "Handle",
    "count": "Кол-во",
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


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        aa, bb = float(a), float(b)
        return abs(aa - bb) <= _FLOAT_TOL * max(1.0, abs(aa), abs(bb))
    if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b):
        return all(_values_equal(x, y) for x, y in zip(a, b))
    return a == b


def common_properties(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Свойства с одинаковым значением у всех выбранных элементов."""
    if not records:
        return {}
    if len(records) == 1:
        return dict(records[0])

    keys = [k for k in records[0] if k != "handle"]
    result: dict[str, Any] = {}
    for key in keys:
        if not all(key in rec for rec in records):
            continue
        first = records[0][key]
        if all(_values_equal(rec[key], first) for rec in records):
            result[key] = first
    return result


def is_similar_entity(reference: dict[str, Any], other: dict[str, Any]) -> bool:
    """Совпадение типа и геометрических размеров (без положения)."""
    ref_type = reference.get("type")
    if other.get("type") != ref_type:
        return False
    if ref_type == "LINE":
        return _values_equal(reference.get("length"), other.get("length"))
    if ref_type == "CIRCLE":
        return _values_equal(reference.get("radius"), other.get("radius"))
    if ref_type == "ARC":
        return (
            _values_equal(reference.get("radius"), other.get("radius"))
            and _values_equal(reference.get("arc_length"), other.get("arc_length"))
        )
    return False


class PropertiesPanel(QFrame):
    property_edited = Signal(str, float)
    select_similar_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("propertiesPanel")
        self._unit = "mm"
        self._block_edits = False
        self._editable_keys: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Свойства объекта")
        title.setObjectName("panelTitle")
        self._count_label = QLabel("")
        self._count_label.setObjectName("mutedLabel")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._count_label)
        layout.addLayout(header)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Свойство", "Значение"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.AnyKeyPressed
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table)

        self._select_similar_btn = QPushButton("Выделить такие же")
        self._select_similar_btn.setVisible(False)
        self._select_similar_btn.clicked.connect(self.select_similar_requested.emit)
        layout.addWidget(self._select_similar_btn)

    def set_unit(self, unit: str) -> None:
        self._unit = unit

    def clear(self) -> None:
        self._block_edits = True
        try:
            self._table.setRowCount(0)
            self._count_label.setText("")
            self._editable_keys.clear()
            self._select_similar_btn.setVisible(False)
        finally:
            self._block_edits = False

    def show_empty(self) -> None:
        self.clear()
        self._count_label.setText("Ничего не выбрано")

    def show_bounding_size(self, width: float, height: float) -> None:
        self._block_edits = True
        try:
            self._table.setRowCount(0)
            self._count_label.setText("Габарит чертежа")
            self._editable_keys.clear()
            self._select_similar_btn.setVisible(False)
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
        finally:
            self._block_edits = False

    def show_properties(self, records: list[dict[str, Any]]) -> None:
        self._block_edits = True
        try:
            self._table.setRowCount(0)
            self._editable_keys.clear()
            if not records:
                self._count_label.setText("Ничего не выбрано")
                self._select_similar_btn.setVisible(False)
                return

            count = len(records)
            self._count_label.setText(f"Выбрано: {count}" if count > 1 else "")

            if count == 1:
                props = dict(records[0])
                entity_type = props.get("type", "")
                if entity_type in ("CIRCLE", "ARC"):
                    self._editable_keys = set(_EDITABLE_CIRCULAR)
                self._select_similar_btn.setVisible(entity_type in _SIMILAR_TYPES)
            else:
                props = common_properties(records)
                self._select_similar_btn.setVisible(False)

            rows: list[tuple[str, str, str]] = [("count", PROP_LABELS["count"], str(count))]
            for key, value in props.items():
                if key in _UNIQUE_KEYS and count > 1:
                    continue
                label = PROP_LABELS.get(key, key)
                rows.append((key, label, self._format_value(key, value)))

            self._table.setRowCount(len(rows))
            for i, (key, label, value) in enumerate(rows):
                self._table.setItem(i, 0, QTableWidgetItem(label))
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item.setData(_ROLE_KEY, key)
                item.setData(_ROLE_FORMATTED, value)
                if key in self._editable_keys:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(i, 1, item)
        finally:
            self._block_edits = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._block_edits or item.column() != 1:
            return
        key = item.data(_ROLE_KEY)
        if key not in self._editable_keys:
            return
        value = parse_length(item.text(), self._unit)
        if value is None:
            self._block_edits = True
            try:
                formatted = item.data(_ROLE_FORMATTED)
                if formatted:
                    item.setText(formatted)
            finally:
                self._block_edits = False
            return
        self.property_edited.emit(str(key), value)

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
