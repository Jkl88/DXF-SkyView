"""Диалог настройки привязок: вкл/откл и порядок приоритета."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from skyview.tools.snap import SNAP_LABELS, SnapMode, SnapSettings


class SnapSettingsDialog(QDialog):
    def __init__(self, settings: SnapSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Привязки")
        self.setMinimumWidth(360)
        self.setMinimumHeight(420)
        self._settings = settings

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Отметьте нужные привязки. Перетаскивайте строки — "
            "чем выше в списке, тем выше приоритет."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._list)

        for mode in settings.priority:
            self._add_item(mode, settings.is_enabled(mode))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_item(self, mode: SnapMode, enabled: bool) -> None:
        item = QListWidgetItem(SNAP_LABELS[mode])
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        item.setFlags(flags)
        item.setCheckState(
            Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked
        )
        item.setData(Qt.ItemDataRole.UserRole, mode)
        self._list.addItem(item)

    def result_settings(self) -> SnapSettings:
        priority: list[SnapMode] = []
        enabled: dict[SnapMode, bool] = {}
        for i in range(self._list.count()):
            item = self._list.item(i)
            mode: SnapMode = item.data(Qt.ItemDataRole.UserRole)
            priority.append(mode)
            enabled[mode] = item.checkState() == Qt.CheckState.Checked
        for mode in SnapMode:
            enabled.setdefault(mode, True)
        return SnapSettings(
            enabled=enabled,
            tolerance_px=self._settings.tolerance_px,
            priority=priority,
        )
