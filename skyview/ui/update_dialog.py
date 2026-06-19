"""Диалог предложения обновления."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from skyview.version import APP_NAME, APP_VERSION


def ask_update(parent: QWidget, remote_version: str) -> str:
    """Спросить пользователя. Возвращает: update | skip | later."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Доступно обновление")
    box.setText("Обновить?!")
    box.setInformativeText(
        f"Доступна новая версия {APP_NAME} {remote_version}.\n"
        f"Установлена версия {APP_VERSION}."
    )
    update_btn = box.addButton("Обновить", QMessageBox.ButtonRole.AcceptRole)
    skip_btn = box.addButton(
        "Пропустить эту версию", QMessageBox.ButtonRole.ActionRole
    )
    later_btn = box.addButton("Позже", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(update_btn)
    box.exec()

    clicked = box.clickedButton()
    if clicked is update_btn:
        return "update"
    if clicked is skip_btn:
        return "skip"
    if clicked is later_btn:
        return "later"
    return "later"
