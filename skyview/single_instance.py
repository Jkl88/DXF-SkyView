"""Один экземпляр приложения — передача путей уже запущенному процессу."""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "DXF-SkyView-SingleInstance-v1"


def paths_from_argv(argv: list[str]) -> list[str]:
    paths: list[str] = []
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        if arg.lower().endswith(".dxf") and os.path.isfile(arg):
            paths.append(os.path.abspath(arg))
    return paths


def send_paths_to_running_instance(paths: list[str]) -> bool:
    if not paths:
        return False

    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(800):
        return False

    payload = "\n".join(paths).encode("utf-8")
    socket.write(payload)
    socket.waitForBytesWritten(2000)
    socket.disconnectFromServer()
    return True


def start_single_instance_server(on_paths: Callable[[list[str]], None]) -> QLocalServer:
    QLocalServer.removeServer(SERVER_NAME)

    server = QLocalServer()

    def _on_new_connection() -> None:
        socket = server.nextPendingConnection()
        if socket is None:
            return
        socket.waitForReadyRead(3000)
        raw = bytes(socket.readAll()).decode("utf-8", errors="replace")
        socket.disconnectFromServer()
        paths = [p for p in raw.split("\n") if p.strip() and os.path.isfile(p)]
        if paths:
            on_paths(paths)

    server.newConnection.connect(_on_new_connection)
    if not server.listen(SERVER_NAME):
        raise RuntimeError(f"Не удалось запустить сервер одиночного экземпляра: {SERVER_NAME}")
    return server
