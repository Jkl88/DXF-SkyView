"""Главное окно приложения."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
    QWidget,
)

from skyview.canvas.view import DxfCanvas
from skyview.dxf.loader import DxfDocument, load_dxf
from skyview.dxf.save import save_dxf
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
    ensure_dxf_file_icon,
    import_dxf,
    is_dxf_associated,
    is_rectangle_creator_available,
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
    is_frozen_app,
    mark_version_skipped,
    perform_update,
    should_offer_update,
)
from skyview.ui.theme import set_theme_mode, toolbar_icon_color


from skyview.version import APP_NAME, APP_VERSION


def _make_measure_icon(dark: bool = True) -> QIcon:
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(toolbar_icon_color(dark))
    pen.setWidthF(1.8)
    p.setPen(pen)
    p.drawLine(4, 20, 20, 4)
    p.drawLine(6, 18, 8, 20)
    p.drawLine(6, 18, 4, 16)
    p.drawLine(18, 6, 20, 8)
    p.drawLine(18, 6, 16, 4)
    p.end()
    return QIcon(pix)


def _make_edit_icon(dark: bool = True) -> QIcon:
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = p.pen()
    pen.setColor(toolbar_icon_color(dark))
    pen.setWidthF(1.8)
    p.setPen(pen)
    p.drawLine(6, 18, 18, 6)
    p.drawLine(16, 4, 20, 8)
    p.drawLine(16, 4, 14, 6)
    p.drawLine(20, 8, 18, 10)
    p.drawRect(4, 8, 10, 12)
    p.end()
    return QIcon(pix)


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
        self._current_doc: DxfDocument | None = None
        self._filepath: str | None = None
        self._modified = False
        self._update_checked_on_start = False
        self._update_thread: UpdateCheckThread | None = None
        self._install_thread: UpdateInstallThread | None = None

        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._canvas = DxfCanvas(self._snap_settings, dark=dark)
        self._properties = PropertiesPanel()
        self._properties.setMinimumWidth(0)

        self._splitter.addWidget(self._canvas)
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
        self._connect_signals()

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

    def _build_menus(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("Файл")
        open_act = QAction("Открыть DXF…", self)
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

        file_menu.addSeparator()

        self._assoc_act = QAction("Открывать .dxf через SkyView", self)
        self._assoc_act.setCheckable(True)
        self._assoc_act.setChecked(is_dxf_associated())
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
        fit_act.triggered.connect(self._canvas.fit_to_view)
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
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22, 22))
        self.addToolBar(toolbar)

        self._measure_btn = QToolButton()
        self._measure_btn.setIcon(_make_measure_icon(self._dark))
        self._measure_btn.setToolTip("Измерить")
        self._measure_btn.setCheckable(True)
        self._measure_btn.clicked.connect(self._toggle_measure)
        toolbar.addWidget(self._measure_btn)

        if is_rectangle_creator_available():
            self._edit_btn = QToolButton()
            self._edit_btn.setIcon(_make_edit_icon(self._dark))
            self._edit_btn.setToolTip("Редактировать в DXF Rectangle Creator")
            self._edit_btn.clicked.connect(self._open_in_editor)
            toolbar.addWidget(self._edit_btn)
        else:
            self._edit_btn = None

    def _build_statusbar(self) -> None:
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Откройте DXF файл (Ctrl+O)")

    def _connect_signals(self) -> None:
        self._canvas.selection_changed.connect(self._on_selection_changed)
        self._canvas.snap_info.connect(self._on_snap_info)
        self._canvas.cursor_moved.connect(self._on_cursor_moved)
        self._canvas.document_modified.connect(self._on_document_modified)
        self._canvas.file_dropped.connect(self._open_dropped_file)
        self._canvas.measure_exit_requested.connect(self._exit_measure_mode)
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._on_system_theme_changed)

    def _toggle_dxf_association(self, checked: bool) -> None:
        if checked:
            ok, message = register_dxf_association()
        else:
            ok, message = unregister_dxf_association()
        self._assoc_act.blockSignals(True)
        self._assoc_act.setChecked(is_dxf_associated())
        self._assoc_act.blockSignals(False)
        if ok and checked:
            ensure_dxf_file_icon()
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
        self._canvas.set_dark_mode(self._dark)
        self._measure_btn.setIcon(_make_measure_icon(self._dark))
        if self._edit_btn is not None:
            self._edit_btn.setIcon(_make_edit_icon(self._dark))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._update_checked_on_start:
            self._update_checked_on_start = True
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
            lambda ok, message, quit_app: self._on_exe_update_finished(
                progress, ok, message, quit_app
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
        ok: bool,
        message: str,
        quit_app: bool,
    ) -> None:
        dialog.close()
        self._show_update_result(ok, message, quit_app)

    def _show_update_result(self, ok: bool, message: str, quit_app: bool) -> None:
        if ok:
            if quit_app:
                if is_frozen_app():
                    # Сразу выходим: .new.exe ждёт завершения этого процесса.
                    QTimer.singleShot(300, lambda: os._exit(0))
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
            self._canvas.update_snap_settings(self._snap_settings)

    def _toggle_measure(self, checked: bool) -> None:
        self._canvas.set_tool("measure" if checked else "select")

    def _open_in_editor(self) -> None:
        if self._current_doc is None:
            QMessageBox.information(
                self,
                "Редактор",
                "Сначала откройте DXF файл.",
            )
            return

        if self._filepath is None:
            if not self._save_file_as():
                return
        elif self._modified:
            if not self._save_file():
                return

        if not self._filepath:
            return

        ok, message = import_dxf(self._filepath)
        if ok:
            self._status.showMessage(
                f"Открыто в DXF Rectangle Creator: {os.path.basename(self._filepath)}"
            )
        else:
            QMessageBox.warning(self, "Редактор", message)

    def _on_document_modified(self) -> None:
        self._modified = True
        self._update_title()
        self._refresh_bounding_properties()

    def _refresh_bounding_properties(self) -> None:
        if self._current_doc is None or self._canvas.has_selection():
            return
        w, h = self._canvas.content_size()
        if w > 0 and h > 0:
            self._properties.show_bounding_size(w, h)

    def _update_title(self) -> None:
        if self._filepath:
            name = os.path.basename(self._filepath)
            star = " *" if self._modified else ""
            self.setWindowTitle(f"{APP_NAME} — {name}{star}")
        else:
            self.setWindowTitle(APP_NAME)

    def _dialog_start_dir(self) -> str:
        if self._filepath:
            folder = os.path.dirname(self._filepath)
            if os.path.isdir(folder):
                return folder
        return last_open_dir()

    def _confirm_discard(self) -> bool:
        if not self._modified:
            return True
        name = os.path.basename(self._filepath) if self._filepath else "документ"
        answer = QMessageBox.question(
            self,
            "Сохранить изменения?",
            f"В файле «{name}» есть несохранённые изменения.\nСохранить перед продолжением?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save_file()
        return True

    def _open_file(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть DXF",
            self._dialog_start_dir(),
            "DXF файлы (*.dxf);;Все файлы (*.*)",
        )
        if path:
            self.load_file(path)

    def _open_dropped_file(self, path: str) -> None:
        if not self._confirm_discard():
            return
        self.load_file(path)

    def load_file(self, path: str) -> None:
        try:
            doc = load_dxf(path)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл:\n{exc}")
            return

        self._current_doc = doc
        self._filepath = path
        self._modified = False
        set_last_open_dir(path)
        self._properties.set_unit(doc.unit_short)
        self._canvas.load_document(doc)
        self._update_title()
        unit = doc.unit_short or doc.unit_name
        self._status.showMessage(
            f"Загружено: {len(doc.records)} объектов | Единицы: {unit}"
        )

    def _save_file(self) -> bool:
        if self._current_doc is None:
            return True
        if not self._filepath:
            return self._save_file_as()
        try:
            remaining = self._canvas.remaining_records()
            save_dxf(self._current_doc, self._filepath, remaining)
            self._modified = False
            set_last_open_dir(self._filepath)
            self._update_title()
            self._status.showMessage(f"Сохранено: {self._filepath}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{exc}")
            return False

    def _save_file_as(self) -> bool:
        if self._current_doc is None:
            return True
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить DXF",
            self._dialog_start_dir(),
            "DXF файлы (*.dxf);;Все файлы (*.*)",
        )
        if not path:
            return False
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        self._filepath = path
        return self._save_file()

    def _on_selection_changed(self, records: list) -> None:
        if records:
            props = [r.properties for r in records]
            self._properties.show_properties(props)
        else:
            w, h = self._canvas.content_size()
            if w > 0 and h > 0:
                self._properties.show_bounding_size(w, h)
            else:
                self._properties.show_empty()

    def _on_snap_info(self, text: str) -> None:
        if text:
            base = self._status.currentMessage().split(" | ")[0]
            self._status.showMessage(f"{base} | {text}")

    def _on_cursor_moved(self, x: float, y: float) -> None:
        if self._current_doc is None:
            return
        unit = self._current_doc.unit_short
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
    def _dxf_from_mime(mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if path.lower().endswith(".dxf"):
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._dxf_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._dxf_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._dxf_from_mime(event.mimeData())
        if path:
            self._open_dropped_file(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def closeEvent(self, event) -> None:
        self._persist_snap_settings()
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    def _undo_delete(self) -> None:
        restored = self._canvas.undo_delete()
        if restored:
            self._status.showMessage(f"Восстановлено объектов: {restored}")

    def _exit_measure_mode(self) -> None:
        if not self._measure_btn.isChecked():
            return
        self._measure_btn.setChecked(False)
        self._canvas.set_tool("select")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._measure_btn.isChecked():
                self._exit_measure_mode()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Delete:
            removed = self._canvas.delete_selected()
            if removed:
                self._status.showMessage(f"Удалено объектов: {removed}")
            event.accept()
            return
        super().keyPressEvent(event)
