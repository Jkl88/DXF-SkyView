"""Тема оформления (светлая / тёмная / по системе)."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from skyview.settings_store import load_theme_mode, save_theme_mode


class ThemeMode(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #313244;
    border-radius: 4px;
}
QMenu {
    background-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #45475a;
    border-radius: 4px;
}
QToolBar {
    background-color: #181825;
    border: none;
    spacing: 6px;
    padding: 4px 8px;
}
QToolButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 12px;
    color: #cdd6f4;
}
QToolButton:hover {
    background-color: #45475a;
}
QToolButton:checked {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-color: #89b4fa;
}
QStatusBar {
    background-color: #181825;
    border-top: 1px solid #313244;
    color: #a6adc8;
}
QFrame#propertiesPanel {
    background-color: #181825;
    border-top: 1px solid #313244;
}
QLabel#panelTitle {
    color: #89b4fa;
    font-weight: 600;
    font-size: 12px;
}
QLabel#mutedLabel {
    color: #a6adc8;
}
QLabel#aboutVersion {
    color: #89b4fa;
    font-size: 14px;
}
QLabel#aboutAuthor {
    color: #a6adc8;
    margin-top: 8px;
}
QTableWidget {
    background-color: #1e1e2e;
    alternate-background-color: #181825;
    gridline-color: #313244;
    border: 1px solid #313244;
    border-radius: 6px;
}
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    border: none;
    padding: 4px 8px;
}
QScrollBar:vertical {
    background: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 5px;
    min-height: 20px;
}
QDialog {
    background-color: #1e1e2e;
}
QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 16px;
    color: #cdd6f4;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:default {
    background-color: #89b4fa;
    color: #1e1e2e;
}
"""

LIGHT_STYLE = """
QMainWindow, QWidget {
    background-color: #eff1f5;
    color: #4c4f69;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #e6e9ef;
    border-bottom: 1px solid #ccd0da;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #dce0e8;
    border-radius: 4px;
}
QMenu {
    background-color: #eff1f5;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #dce0e8;
    border-radius: 4px;
}
QToolBar {
    background-color: #e6e9ef;
    border: none;
    spacing: 6px;
    padding: 4px 8px;
}
QToolButton {
    background-color: #dce0e8;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    padding: 6px 12px;
    color: #4c4f69;
}
QToolButton:hover {
    background-color: #ccd0da;
}
QToolButton:checked {
    background-color: #1e66f5;
    color: #eff1f5;
    border-color: #1e66f5;
}
QStatusBar {
    background-color: #e6e9ef;
    border-top: 1px solid #ccd0da;
    color: #6c6f85;
}
QFrame#propertiesPanel {
    background-color: #e6e9ef;
    border-top: 1px solid #ccd0da;
}
QLabel#panelTitle {
    color: #1e66f5;
    font-weight: 600;
    font-size: 12px;
}
QLabel#mutedLabel {
    color: #6c6f85;
}
QLabel#aboutVersion {
    color: #1e66f5;
    font-size: 14px;
}
QLabel#aboutAuthor {
    color: #6c6f85;
    margin-top: 8px;
}
QTableWidget {
    background-color: #eff1f5;
    alternate-background-color: #e6e9ef;
    gridline-color: #ccd0da;
    border: 1px solid #ccd0da;
    border-radius: 6px;
}
QHeaderView::section {
    background-color: #dce0e8;
    color: #4c4f69;
    border: none;
    padding: 4px 8px;
}
QScrollBar:vertical {
    background: #e6e9ef;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #ccd0da;
    border-radius: 5px;
    min-height: 20px;
}
QDialog {
    background-color: #eff1f5;
}
QPushButton {
    background-color: #dce0e8;
    border: 1px solid #ccd0da;
    border-radius: 6px;
    padding: 8px 16px;
    color: #4c4f69;
}
QPushButton:hover {
    background-color: #ccd0da;
}
QPushButton:default {
    background-color: #1e66f5;
    color: #eff1f5;
}
"""


def is_system_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    hints = app.styleHints()
    scheme = hints.colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    bg = app.palette().color(QPalette.ColorRole.Window)
    return bg.lightness() < 128


def resolve_is_dark(mode: str | ThemeMode | None = None) -> bool:
    if mode is None:
        mode = load_theme_mode()
    if isinstance(mode, ThemeMode):
        mode = mode.value
    if mode == ThemeMode.LIGHT.value:
        return False
    if mode == ThemeMode.DARK.value:
        return True
    return is_system_dark()


def is_dark_mode() -> bool:
    """Текущая активная тема (с учётом настройки пользователя)."""
    return resolve_is_dark()


def apply_theme(app: QApplication, mode: str | ThemeMode | None = None) -> bool:
    """Применить тему. Возвращает True если тёмная."""
    if mode is None:
        mode = load_theme_mode()
    if isinstance(mode, ThemeMode):
        mode = mode.value
    dark = resolve_is_dark(mode)
    app.setStyleSheet(DARK_STYLE if dark else LIGHT_STYLE)
    return dark


def set_theme_mode(app: QApplication, mode: str | ThemeMode) -> bool:
    """Сохранить и применить режим темы. Возвращает True если тёмная."""
    if isinstance(mode, ThemeMode):
        mode = mode.value
    save_theme_mode(mode)
    return apply_theme(app, mode)


def canvas_background(dark: bool | None = None) -> QColor:
    if dark is None:
        dark = is_dark_mode()
    return QColor(30, 30, 46) if dark else QColor(250, 250, 252)


def overlay_line_color(dark: bool | None = None) -> QColor:
    if dark is None:
        dark = is_dark_mode()
    return QColor(200, 200, 200) if dark else QColor(80, 85, 100)


def overlay_text_color(dark: bool | None = None) -> QColor:
    if dark is None:
        dark = is_dark_mode()
    return QColor(220, 220, 220) if dark else QColor(60, 64, 80)


def guide_line_color(dark: bool | None = None) -> QColor:
    if dark is None:
        dark = is_dark_mode()
    return QColor(210, 210, 210, 220) if dark else QColor(90, 95, 110, 220)


def toolbar_icon_color(dark: bool | None = None) -> QColor:
    if dark is None:
        dark = is_dark_mode()
    return QColor(235, 235, 240) if dark else QColor(50, 54, 70)


def adjust_entity_color(color: QColor, dark: bool | None = None) -> QColor:
    """Подстроить цвет объекта под фон (ACI 7 = белый/чёрный)."""
    if dark is None:
        dark = is_dark_mode()
    if dark:
        return color

    lum = color.lightness()
    if lum >= 240:
        return QColor(28, 32, 40)
    if lum >= 200:
        factor = 0.35
        return QColor(
            max(50, int(color.red() * factor)),
            max(50, int(color.green() * factor)),
            max(50, int(color.blue() * factor)),
        )
    if lum >= 170 and color.saturation() < 40:
        return QColor(
            max(60, int(color.red() * 0.55)),
            max(60, int(color.green() * 0.55)),
            max(60, int(color.blue() * 0.55)),
        )
    return color
