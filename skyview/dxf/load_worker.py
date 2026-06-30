"""Фоновая загрузка CAD-файлов."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class CadLoadWorker(QThread):
    finished_ok = Signal(object, str)
    failed = Signal(str)

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self._path = path

    def run(self) -> None:
        from skyview.dxf.loader import load_cad

        try:
            doc = load_cad(self._path)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(doc, self._path)
