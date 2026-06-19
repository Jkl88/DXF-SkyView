"""Тема оформления (светлая/тёмная по системе)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


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


def is_dark_mode() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    hints = app.styleHints()
    scheme = hints.colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    # Fallback: яркость фона палитры
    bg = app.palette().color(QPalette.ColorRole.Window)
    return bg.lightness() < 128


def apply_theme(app: QApplication) -> bool:
    """Применить тему. Возвращает True если тёмная."""
    dark = is_dark_mode()
    app.setStyleSheet(DARK_STYLE if dark else LIGHT_STYLE)
    return dark


def canvas_background() -> QColor:
    return QColor(30, 30, 46) if is_dark_mode() else QColor(250, 250, 252)
