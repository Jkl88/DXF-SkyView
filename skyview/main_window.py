"""Главное окно приложения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from skyview.canvas.view import DxfCanvas
from skyview.cad_files import (
    absolute_path,
    compare_path_key,
    is_cad_file,
    open_file_filter,
    save_file_filter,
    save_path_for_cad,
)
from skyview.settings_store import (
    last_open_dir,
    load_snap_enabled,
    load_snap_priority,
    load_theme_mode,
    save_snap_enabled,
    save_snap_priority,
    save_theme_mode,
    set_last_open_dir,
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
)
from skyview.integration import (
    import_dxf,
    is_dxf_associated,
    is_dwg_associated,
    register_dxf_association,
    unregister_dxf_association,
)
from skyview.resources import app_icon
from skyview.tools.snap import SnapMode, SnapSettings
from skyview.ui.about_dialog import AboutDialog
from skyview.ui.properties_panel import PropertiesPanel
from skyview.ui.snap_settings_dialog import SnapSettingsDialog
from skyview.ui.update_dialog import ask_update
from skyview.updater import (
    UpdateCheckThread,
    UpdateInstallThread,
    apply_downloaded_release,
    is_frozen_app,
    mark_version_skipped,
    perform_update,
    should_offer_update,
)
from skyview.ui.theme import set_theme_mode


from skyview.version import APP_NAME, APP_VERSION

_EMOJI_FONTS = (
    "Segoe UI Emoji",
    "Segoe UI Symbol",
    "Noto Color Emoji",
    "Apple Color Emoji",
)
_TOOL_ICON_SIZE = 28


def _make_emoji_icon(emoji: str, size: int = _TOOL_ICON_SIZE) -> QIcon:
    """Отрисовать эмодзи в pixmap — QToolButton на Windows не показывает их как текст."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    font = QFont()
    font.setPointSize(max(14, int(size * 0.78)))
    for family in _EMOJI_FONTS:
        font.setFamily(family)
        if QFontMetrics(font).horizontalAdvance(emoji) > 0:
            break

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    metrics = QFontMetrics(font)
    x = (size - metrics.horizontalAdvance(emoji)) // 2
    y = (size - metrics.height()) // 2 + metrics.ascent()
    painter.drawText(x, y, emoji)
    painter.end()
    return QIcon(pix)


def _style_emoji_toolbutton(btn: QToolButton, emoji: str) -> None:
    btn.setIcon(_make_emoji_icon(emoji))
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    btn.setIconSize(QSize(_TOOL_ICON_SIZE, _TOOL_ICON_SIZE))
    btn.setFixedSize(40, 32)


@dataclass
class _DocTab:
    canvas: DxfCanvas
    filepath: str | None = None
    modified: bool = False

    def display_name(self) -> str:
        if self.filepath:
            return os.path.basename(self.filepath)
        return "Без имени"

    def tab_text(self) -> str:
        star = " *" if self.modified else ""
        return f"{self.display_name()}{star}"


class MainWindow(QMainWindow):
    def __init__(self, dark: bool = True, theme_mode: str = THEME_SYSTEM):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        window_icon = app_icon()
        if not window_icon.isNull():
            self.setWindowIcon(window_icon)

        self._theme_mode = theme_mode
        self._dark = dark

        self._snap_settings = self._load_snap_settings()
        self._tab_docs: dict[DxfCanvas, _DocTab] = {}
        self._connected_canvas: DxfCanvas | None = None
        self._update_checked_on_start = False
        self._update_thread: UpdateCheckThread | None = None
        self._install_thread: UpdateInstallThread | None = None
        self._load_worker = None
        self._toolbar: QToolBar | None = None
        self._edit_btn: QToolButton | None = None

        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._properties = PropertiesPanel()
        self._properties.setMinimumWidth(0)

        self._splitter.addWidget(self._tabs)
        self._splitter.addWidget(self._properties)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([900, 280])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, True)

        layout.addWidget(self._splitter)

        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()

    @staticmethod
    def _load_snap_settings() -> SnapSettings:
        enabled = load_snap_enabled()
        return SnapSettings(
            enabled=enabled if enabled else {m: True for m in SnapMode},
            priority=load_snap_priority(),
        )

    def _persist_snap_settings(self) -> None:
        save_snap_priority(self._snap_settings.priority)
        save_snap_enabled(self._snap_settings.enabled)

    def _active_canvas(self) -> DxfCanvas | None:
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, DxfCanvas) else None

    def _active_tab(self) -> _DocTab | None:
        canvas = self._active_canvas()
        if canvas is None:
            return None
        return self._tab_docs.get(canvas)

    def _find_tab_index_by_path(self, path: str) -> int | None:
        key = compare_path_key(path)
        for index in range(self._tabs.count()):
            widget = self._tabs.widget(index)
            if not isinstance(widget, DxfCanvas):
                continue
            tab = self._tab_docs.get(widget)
            if tab and tab.filepath and compare_path_key(tab.filepath) == key:
                return index
        return None

    def _tab_index_for_canvas(self, canvas: DxfCanvas) -> int | None:
        for index in range(self._tabs.count()):
            if self._tabs.widget(index) is canvas:
                return index
        return None

    def _create_tab_canvas(self) -> DxfCanvas:
        canvas = DxfCanvas(self._snap_settings, dark=self._dark)
        canvas.file_dropped.connect(self.open_path)
        canvas.document_modified.connect(
            lambda canvas=canvas: self._on_tab_modified(canvas)
        )
        return canvas

    def _connect_canvas(self, canvas: DxfCanvas) -> None:
        canvas.selection_changed.connect(self._on_selection_changed)
        canvas.snap_info.connect(self._on_snap_info)
        canvas.cursor_moved.connect(self._on_cursor_moved)
        canvas.measure_exit_requested.connect(self._exit_measure_mode)

    def _disconnect_canvas(self, canvas: DxfCanvas) -> None:
        canvas.selection_changed.disconnect(self._on_selection_changed)
        canvas.snap_info.disconnect(self._on_snap_info)
        canvas.cursor_moved.disconnect(self._on_cursor_moved)
        canvas.measure_exit_requested.disconnect(self._exit_measure_mode)

    def _connect_active_canvas(self) -> None:
        canvas = self._active_canvas()
        if canvas is self._connected_canvas:
            return
        if self._connected_canvas is not None:
            self._disconnect_canvas(self._connected_canvas)
        self._connected_canvas = canvas
        if canvas is not None:
            self._connect_canvas(canvas)
            self._measure_btn.setChecked(canvas.tool == "measure")
            self._on_selection_changed(canvas.selected_records())

    def _on_tab_changed(self, _index: int) -> None:
        self._connect_active_canvas()
        tab = self._active_tab()
        if tab is None:
            self._properties.show_empty()
            self._update_window_title()
            self._status.showMessage("Откройте DXF файл (Ctrl+O)")
            return
        if tab.canvas.document:
            self._properties.set_unit(tab.canvas.document.unit_short)
        self._update_status_for_tab(tab)
        self._update_window_title()

    def bring_to_front(self) -> None:
        state = self.windowState()
        if state & Qt.WindowState.WindowMinimized:
            self.setWindowState(state & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def open_paths(self, paths: list[str]) -> None:
        for path in paths:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            return

        existing = self._find_tab_index_by_path(path)
        if existing is not None:
            self._tabs.setCurrentIndex(existing)
            self.bring_to_front()
            return

        abs_path = absolute_path(path)
        self._start_load(abs_path)

    def _start_load(self, abs_path: str) -> None:
        from skyview.dxf.load_worker import CadLoadWorker

        if self._load_worker is not None and self._load_worker.isRunning():
            QMessageBox.information(
                self,
                APP_NAME,
                "Дождитесь завершения текущей загрузки файла.",
            )
            return

        name = os.path.basename(abs_path)
        progress = QProgressDialog(f"Загрузка {name}…", None, 0, 0, self)
        progress.setWindowTitle(APP_NAME)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        worker = CadLoadWorker(abs_path, self)
        worker.finished_ok.connect(
            lambda doc, loaded_path, dlg=progress, w=worker: self._on_load_finished(
                doc, loaded_path, dlg, w
            )
        )
        worker.failed.connect(
            lambda msg, loaded_path=abs_path, dlg=progress, w=worker: self._on_load_failed(
                msg, loaded_path, dlg, w
            )
        )
        self._load_worker = worker
        worker.start()

    def _on_load_finished(self, doc, path: str, progress: QProgressDialog, worker) -> None:
        progress.close()
        worker.deleteLater()
        if worker is self._load_worker:
            self._load_worker = None

        canvas = self._create_tab_canvas()
        tab = _DocTab(canvas=canvas, filepath=path, modified=False)
        self._tab_docs[canvas] = tab

        index = self._tabs.addTab(canvas, tab.tab_text())
        self._tabs.setCurrentIndex(index)
        self._properties.set_unit(doc.unit_short)
        canvas.load_document(doc)
        set_last_open_dir(path)
        self._update_status_for_tab(tab)
        self._update_window_title()
        self.bring_to_front()

    def _on_load_failed(
        self, message: str, path: str, progress: QProgressDialog, worker
    ) -> None:
        progress.close()
        worker.deleteLater()
        if worker is self._load_worker:
            self._load_worker = None
        QMessageBox.critical(
            self,
            "Ошибка",
            f"Не удалось открыть файл:\n{os.path.basename(path)}\n\n{message}",
        )

    def _on_tab_modified(self, canvas: DxfCanvas) -> None:
        tab = self._tab_docs.get(canvas)
        if tab is None:
            return
        tab.modified = True
        index = self._tab_index_for_canvas(canvas)
        if index is not None:
            self._tabs.setTabText(index, tab.tab_text())
        if canvas is self._active_canvas():
            self._update_window_title()
            self._refresh_bounding_properties()

    def _update_tab_text(self, canvas: DxfCanvas) -> None:
        tab = self._tab_docs.get(canvas)
        index = self._tab_index_for_canvas(canvas)
        if tab is None or index is None:
            return
        self._tabs.setTabText(index, tab.tab_text())

    def _update_status_for_tab(self, tab: _DocTab) -> None:
        doc = tab.canvas.document
        if doc is None:
            return
        unit = doc.unit_short or doc.unit_name
        self._status.showMessage(
            f"Загружено: {len(doc.records)} объектов | Единицы: {unit}"
        )

    def _build_menus(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("Файл")
        open_act = QAction("Открыть…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._open_file)
        file_menu.addAction(open_act)

        self._save_act = QAction("Сохранить", self)
        self._save_act.setShortcut(QKeySequence.StandardKey.Save)
        self._save_act.triggered.connect(self._save_file)
        file_menu.addAction(self._save_act)

        self._save_as_act = QAction("Сохранить как…", self)
        self._save_as_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._save_as_act.triggered.connect(self._save_file_as)
        file_menu.addAction(self._save_as_act)

        close_tab_act = QAction("Закрыть вкладку", self)
        close_tab_act.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_act.triggered.connect(self._close_current_tab)
        file_menu.addAction(close_tab_act)

        file_menu.addSeparator()

        self._assoc_act = QAction("Открывать .dxf и .dwg через SkyView", self)
        self._assoc_act.setCheckable(True)
        self._assoc_act.setChecked(is_dxf_associated() or is_dwg_associated())
        self._assoc_act.triggered.connect(self._toggle_dxf_association)
        file_menu.addAction(self._assoc_act)

        file_menu.addSeparator()

        exit_act = QAction("Выход", self)
        exit_act.setShortcut(QKeySequence.StandardKey.Quit)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        view_menu = menu.addMenu("Вид")
        fit_act = QAction("Вписать в окно", self)
        fit_act.setShortcut("F")
        fit_act.triggered.connect(self._fit_active_tab)
        view_menu.addAction(fit_act)

        undo_act = QAction("Отменить удаление", self)
        undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        undo_act.triggered.connect(self._undo_delete)
        view_menu.addAction(undo_act)

        snap_act = QAction("Привязки…", self)
        snap_act.triggered.connect(self._open_snap_settings)
        view_menu.addAction(snap_act)

        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Тема")
        self._theme_actions: dict[str, QAction] = {}
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for mode, label in (
            (THEME_SYSTEM, "Системная"),
            (THEME_LIGHT, "Светлая"),
            (THEME_DARK, "Тёмная"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(mode == self._theme_mode)
            theme_group.addAction(act)
            act.triggered.connect(lambda _checked=False, m=mode: self._set_theme_mode(m))
            theme_menu.addAction(act)
            self._theme_actions[mode] = act

        help_menu = menu.addMenu("Справка")
        check_updates_act = QAction("Проверить обновления…", self)
        check_updates_act.triggered.connect(self._check_updates_manual)
        help_menu.addAction(check_updates_act)
        about_act = QAction("О программе", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Инструменты")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self._toolbar = toolbar

        self._measure_btn = QToolButton()
        _style_emoji_toolbutton(self._measure_btn, "📐")
        self._measure_btn.setToolTip("Измерить")
        self._measure_btn.setCheckable(True)
        self._measure_btn.clicked.connect(self._toggle_measure)
        toolbar.addWidget(self._measure_btn)

    def _maybe_add_edit_toolbar_button(self) -> None:
        if self._edit_btn is not None or self._toolbar is None:
            return
        from skyview.integration import is_rectangle_creator_available

        if not is_rectangle_creator_available():
            return
        self._edit_btn = QToolButton()
        _style_emoji_toolbutton(self._edit_btn, "✏️")
        self._edit_btn.setToolTip("Редактировать в DXF Rectangle Creator")
        self._edit_btn.clicked.connect(self._open_in_editor)
        self._toolbar.addWidget(self._edit_btn)

    def _deferred_startup_tasks(self) -> None:
        self._maybe_add_edit_toolbar_button()

    def _build_statusbar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Откройте DXF файл (Ctrl+O)")

    def _fit_active_tab(self) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.fit_to_view()

    def _toggle_dxf_association(self, checked: bool) -> None:
        if checked:
            ok, message = register_dxf_association()
        else:
            ok, message = unregister_dxf_association()
        self._assoc_act.blockSignals(True)
        self._assoc_act.setChecked(is_dxf_associated() or is_dwg_associated())
        self._assoc_act.blockSignals(False)
        if ok:
            QMessageBox.information(self, "Ассоциация файлов", message)
        else:
            QMessageBox.warning(self, "Ассоциация файлов", message)

    def _on_system_theme_changed(self, _scheme) -> None:
        if self._theme_mode == THEME_SYSTEM:
            self._apply_theme(THEME_SYSTEM)

    def _set_theme_mode(self, mode: str) -> None:
        if mode == self._theme_mode:
            for key, act in self._theme_actions.items():
                act.setChecked(key == mode)
            return
        self._apply_theme(mode)

    def _apply_theme(self, mode: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._theme_mode = mode
        save_theme_mode(mode)
        self._dark = set_theme_mode(app, mode)
        for key, act in self._theme_actions.items():
            act.setChecked(key == mode)
        for canvas in self._tab_docs:
            canvas.set_dark_mode(self._dark)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._update_checked_on_start:
            self._update_checked_on_start = True
            QTimer.singleShot(0, self._deferred_startup_tasks)
            QTimer.singleShot(800, self._check_updates_on_start)

    def _check_updates_on_start(self) -> None:
        self._start_update_check(manual=False)

    def _check_updates_manual(self) -> None:
        self._start_update_check(manual=True)

    def _start_update_check(self, manual: bool) -> None:
        if self._update_thread is not None and self._update_thread.isRunning():
            return
        self._update_thread = UpdateCheckThread()
        self._update_thread.finished_check.connect(
            lambda remote: self._on_update_checked(remote, manual)
        )
        self._update_thread.start()

    def _on_update_checked(self, remote_version: object, manual: bool) -> None:
        remote = remote_version if isinstance(remote_version, str) else None
        if remote is None:
            if manual:
                QMessageBox.warning(
                    self,
                    "Обновления",
                    "Не удалось проверить обновления.\nПроверьте подключение к интернету.",
                )
            return

        if not should_offer_update(remote):
            if manual:
                QMessageBox.information(
                    self,
                    "Обновления",
                    f"Установлена актуальная версия {APP_VERSION}.",
                )
            return

        choice = ask_update(self, remote)
        if choice == "skip":
            mark_version_skipped(remote)
            return
        if choice != "update":
            return

        if is_frozen_app():
            self._start_exe_update(remote)
            return

        ok, message, quit_app = perform_update(remote)
        self._show_update_result(ok, message, quit_app)

    def _start_exe_update(self, remote_version: str) -> None:
        if self._install_thread is not None and self._install_thread.isRunning():
            return

        progress = QProgressDialog("Загрузка обновления…", None, 0, 0, self)
        progress.setWindowTitle("Обновление")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        self._install_thread = UpdateInstallThread(remote_version, self)
        self._install_thread.progress.connect(
            lambda done, total: self._on_update_download_progress(progress, done, total)
        )
        self._install_thread.finished_install.connect(
            lambda ok, message, installer_path: self._on_exe_update_finished(
                progress, ok, message, installer_path
            )
        )
        self._install_thread.start()

    def _on_update_download_progress(
        self, dialog: QProgressDialog, done: int, total: int
    ) -> None:
        if total > 0:
            if dialog.maximum() != total:
                dialog.setRange(0, total)
            dialog.setValue(min(done, total))
            dialog.setLabelText(
                f"Загрузка обновления… {done * 100 // total}%"
            )
        else:
            dialog.setRange(0, 0)

    def _on_exe_update_finished(
        self,
        dialog: QProgressDialog,
        downloaded: bool,
        message: str,
        installer_path: object,
    ) -> None:
        dialog.close()
        if not downloaded:
            self._show_update_result(False, message, False)
            return

        if not installer_path:
            self._show_update_result(False, "Файл обновления не получен.", False)
            return

        try:
            path = Path(str(installer_path))
            hwnd = int(self.winId())
            ok, launch_message = apply_downloaded_release(path, hwnd)
        except Exception as exc:
            self._show_update_result(
                False,
                f"Не удалось запустить установку обновления:\n{exc}",
                False,
            )
            return

        if ok:
            QApplication.processEvents()
        self._show_update_result(ok, launch_message, ok)

    def _show_update_result(self, ok: bool, message: str, quit_app: bool) -> None:
        if ok:
            if quit_app:
                if is_frozen_app():
                    QMessageBox.information(
                        self,
                        "Обновление",
                        f"{message}\n\nПриложение закроется для установки.\n"
                        "Подтвердите запрос UAC, если появится.",
                    )
                    QTimer.singleShot(400, lambda: os._exit(0))
                    return
                QMessageBox.information(self, "Обновление", message)
                QApplication.instance().quit()
            else:
                QMessageBox.information(
                    self,
                    "Обновление",
                    f"{message}\n\nПерезапустите приложение.",
                )
        else:
            QMessageBox.critical(self, "Обновление", message)

    def _open_snap_settings(self) -> None:
        dialog = SnapSettingsDialog(self._snap_settings, self)
        if dialog.exec():
            self._snap_settings = dialog.result_settings()
            self._persist_snap_settings()
            for canvas in self._tab_docs:
                canvas.update_snap_settings(self._snap_settings)

    def _toggle_measure(self, checked: bool) -> None:
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_tool("measure" if checked else "select")

    def _open_in_editor(self) -> None:
        tab = self._active_tab()
        if tab is None or tab.canvas.document is None:
            QMessageBox.information(
                self,
                "Редактор",
                "Сначала откройте DXF файл.",
            )
            return

        if tab.filepath is None:
            if not self._save_file_as():
                return
        elif tab.modified:
            if not self._save_file():
                return

        if not tab.filepath:
            return

        ok, message = import_dxf(tab.filepath)
        if ok:
            self._status.showMessage(
                f"Открыто в DXF Rectangle Creator: {os.path.basename(tab.filepath)}"
            )
        else:
            QMessageBox.warning(self, "Редактор", message)

    def _refresh_bounding_properties(self) -> None:
        canvas = self._active_canvas()
        if canvas is None or canvas.document is None or canvas.has_selection():
            return
        w, h = canvas.content_size()
        if w > 0 and h > 0:
            self._properties.show_bounding_size(w, h)

    def _update_window_title(self) -> None:
        tab = self._active_tab()
        extra = ""
        if self._tabs.count() > 1:
            extra = f" ({self._tabs.count()} вкладок)"
        if tab and tab.filepath:
            star = " *" if tab.modified else ""
            self.setWindowTitle(f"{APP_NAME} — {tab.display_name()}{star}{extra}")
        else:
            self.setWindowTitle(f"{APP_NAME}{extra}")

    def _dialog_start_dir(self) -> str:
        tab = self._active_tab()
        if tab and tab.filepath:
            folder = os.path.dirname(tab.filepath)
            if os.path.isdir(folder):
                return folder
        return last_open_dir()

    def _confirm_close_tab(self, tab: _DocTab) -> bool:
        if not tab.modified:
            return True
        name = tab.display_name()
        answer = QMessageBox.question(
            self,
            "Сохранить изменения?",
            f"В файле «{name}» есть несохранённые изменения.\nСохранить перед закрытием?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save_tab(tab)
        return True

    def _close_tab(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if not isinstance(widget, DxfCanvas):
            return
        tab = self._tab_docs.get(widget)
        if tab is None:
            return
        if not self._confirm_close_tab(tab):
            return
        if widget is self._connected_canvas:
            self._disconnect_canvas(widget)
            self._connected_canvas = None
        del self._tab_docs[widget]
        self._tabs.removeTab(index)
        widget.deleteLater()

    def _close_current_tab(self) -> None:
        index = self._tabs.currentIndex()
        if index >= 0:
            self._close_tab(index)

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть файл",
            self._dialog_start_dir(),
            open_file_filter(),
        )
        if path:
            self.open_path(path)

    def load_file(self, path: str) -> None:
        """Совместимость: открыть файл во вкладке."""
        self.open_path(path)

    def _save_tab(self, tab: _DocTab) -> bool:
        if tab.canvas.document is None:
            return True
        if not tab.filepath:
            return self._save_file_as_for_tab(tab)
        save_path = save_path_for_cad(tab.filepath)
        try:
            from skyview.dxf.save import save_dxf

            remaining = tab.canvas.remaining_records()
            save_dxf(tab.canvas.document, save_path, remaining)
            tab.filepath = absolute_path(save_path)
            tab.modified = False
            set_last_open_dir(tab.filepath)
            self._update_tab_text(tab.canvas)
            if tab.canvas is self._active_canvas():
                self._update_window_title()
                self._status.showMessage(f"Сохранено: {tab.filepath}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{exc}")
            return False

    def _save_file(self) -> bool:
        tab = self._active_tab()
        if tab is None:
            return True
        return self._save_tab(tab)

    def _save_file_as_for_tab(self, tab: _DocTab) -> bool:
        if tab.canvas.document is None:
            return True
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить DXF",
            self._dialog_start_dir(),
            save_file_filter(),
        )
        if not path:
            return False
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        tab.filepath = absolute_path(path)
        return self._save_tab(tab)

    def _save_file_as(self) -> bool:
        tab = self._active_tab()
        if tab is None:
            return True
        return self._save_file_as_for_tab(tab)

    def _on_selection_changed(self, records: list) -> None:
        if records:
            props = [r.get_properties() for r in records]
            self._properties.show_properties(props)
        else:
            canvas = self._active_canvas()
            if canvas is not None:
                w, h = canvas.content_size()
                if w > 0 and h > 0:
                    self._properties.show_bounding_size(w, h)
                else:
                    self._properties.show_empty()
            else:
                self._properties.show_empty()

    def _on_snap_info(self, text: str) -> None:
        if text:
            base = self._status.currentMessage().split(" | ")[0]
            self._status.showMessage(f"{base} | {text}")

    def _on_cursor_moved(self, x: float, y: float) -> None:
        tab = self._active_tab()
        if tab is None or tab.canvas.document is None:
            return
        unit = tab.canvas.document.unit_short
        suffix = f" {unit}" if unit else ""
        base_parts = self._status.currentMessage().split(" | ")
        base = base_parts[0] if base_parts else ""
        snap = ""
        for part in base_parts[1:]:
            if part.startswith("Привязка"):
                snap = f" | {part}"
        self._status.showMessage(f"{base} | X: {x:.3f}{suffix}  Y: {y:.3f}{suffix}{snap}")

    def _show_about(self) -> None:
        AboutDialog(self).exec()

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
            self.open_path(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def closeEvent(self, event) -> None:
        self._persist_snap_settings()
        for index in range(self._tabs.count() - 1, -1, -1):
            widget = self._tabs.widget(index)
            if not isinstance(widget, DxfCanvas):
                continue
            tab = self._tab_docs.get(widget)
            if tab is None:
                continue
            if not self._confirm_close_tab(tab):
                event.ignore()
                return
        event.accept()

    def _undo_delete(self) -> None:
        canvas = self._active_canvas()
        if canvas is None:
            return
        restored = canvas.undo_delete()
        if restored:
            self._status.showMessage(f"Восстановлено объектов: {restored}")

    def _exit_measure_mode(self) -> None:
        if not self._measure_btn.isChecked():
            return
        self._measure_btn.setChecked(False)
        canvas = self._active_canvas()
        if canvas is not None:
            canvas.set_tool("select")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._measure_btn.isChecked():
                self._exit_measure_mode()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Delete:
            canvas = self._active_canvas()
            if canvas is not None:
                removed = canvas.delete_selected()
                if removed:
                    self._status.showMessage(f"Удалено объектов: {removed}")
            event.accept()
            return
        super().keyPressEvent(event)
