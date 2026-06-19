"""Проверка и установка обновлений с GitHub."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices

from skyview.resources import app_root, install_root
from skyview.settings_store import load_skipped_update_versions, skip_update_version
from skyview.version import (
    APP_VERSION,
    GITHUB_API_BASE,
    GITHUB_BRANCH,
    GITHUB_URL,
    RELEASE_EXE_NAME,
    REMOTE_VERSION_URL,
)

_VERSION_RE = re.compile(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']')
_GITHUB_HOSTS = frozenset({"github.com", "objects.githubusercontent.com"})


def parse_version(text: str) -> str | None:
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    return version_tuple(remote) > version_tuple(local)


def is_frozen_app() -> bool:
    return getattr(sys, "frozen", False)


def _github_get_json(url: str, timeout: float = 15.0) -> dict | list | None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"DXF-SkyView/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _release_tag_version(tag_name: str) -> str:
    tag = tag_name.strip()
    if tag.lower().startswith("v"):
        return tag[1:]
    return tag


def _find_exe_asset(release: dict) -> str | None:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") == RELEASE_EXE_NAME:
            url = asset.get("browser_download_url")
            if isinstance(url, str) and _is_safe_github_url(url):
                return url
    return None


def _is_safe_github_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in _GITHUB_HOSTS


def fetch_remote_version(timeout: float = 12.0) -> str | None:
    request = urllib.request.Request(
        REMOTE_VERSION_URL,
        headers={"User-Agent": f"DXF-SkyView/{APP_VERSION}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return parse_version(text)


def fetch_release_exe_url(version: str) -> tuple[str | None, str]:
    for tag in (f"v{version}", version):
        release = _github_get_json(f"{GITHUB_API_BASE}/releases/tags/{tag}")
        if isinstance(release, dict):
            url = _find_exe_asset(release)
            if url:
                return url, ""

    latest = _github_get_json(f"{GITHUB_API_BASE}/releases/latest")
    if isinstance(latest, dict):
        if _release_tag_version(str(latest.get("tag_name", ""))) == version:
            url = _find_exe_asset(latest)
            if url:
                return url, ""

    return (
        None,
        f"На GitHub не найден релиз {version} с файлом {RELEASE_EXE_NAME}.\n"
        f"Страница релизов: {GITHUB_URL}/releases",
    )


def should_offer_update(remote_version: str) -> bool:
    if not is_newer(remote_version, APP_VERSION):
        return False
    return remote_version not in load_skipped_update_versions()


def git_source_root() -> Path | None:
    root = app_root()
    if (root / ".git").is_dir():
        return root
    return None


def run_git_update() -> tuple[bool, str]:
    root = git_source_root()
    if root is None:
        return False, "Репозиторий Git не найден."
    try:
        subprocess.run(
            ["git", "fetch", "origin", GITHUB_BRANCH],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", GITHUB_BRANCH],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        msg = (result.stdout or "").strip()
        return True, msg or "Обновление завершено."
    except FileNotFoundError:
        return False, "Git не установлен в системе."
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        return False, err or "Не удалось обновить через Git."


def _download_file(
    url: str,
    destination: Path,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 600.0,
) -> None:
    if not _is_safe_github_url(url):
        raise ValueError("Недопустимый адрес загрузки.")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"DXF-SkyView/{APP_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total_header = response.headers.get("Content-Length")
        total = int(total_header) if total_header else -1
        if progress is not None:
            progress(0, total)

        destination.parent.mkdir(parents=True, exist_ok=True)
        received = 0
        chunk_size = 256 * 1024
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                received += len(chunk)
                if progress is not None:
                    progress(received, total)


def _create_windows_replacer(
    target_exe: Path,
    new_exe: Path,
    pid: int,
) -> Path:
    bat_path = Path(tempfile.gettempdir()) / f"skyview_update_{pid}.bat"
    lines = [
        "@echo off",
        "setlocal",
        f'set "TARGET={target_exe}"',
        f'set "NEW={new_exe}"',
        f"set PID={pid}",
        ":wait",
        'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul',
        "if %errorlevel%==0 (",
        "    timeout /t 1 /nobreak >nul",
        "    goto wait",
        ")",
        'if not exist "%NEW%" exit /b 1',
        'copy /y "%NEW%" "%TARGET%" >nul',
        'if exist "%NEW%" del /f /q "%NEW%"',
        'start "" "%TARGET%"',
        'del /f /q "%~f0"',
    ]
    bat_path.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")
    return bat_path


def run_exe_update(
    remote_version: str,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[bool, str, bool]:
    """Скачать релиз и подготовить замену exe. Третье значение — завершить приложение."""
    if not is_frozen_app():
        return False, "Автообновление exe доступно только в собранной версии.", False
    if sys.platform != "win32":
        return False, "Автообновление exe поддерживается только в Windows.", False

    download_url, error = fetch_release_exe_url(remote_version)
    if not download_url:
        return False, error, False

    target_exe = Path(sys.executable).resolve()
    new_exe = target_exe.with_name(f"{target_exe.stem}.new.exe")

    if new_exe.exists():
        try:
            new_exe.unlink()
        except OSError:
            return False, "Не удалось подготовить файл обновления.", False

    try:
        _download_file(download_url, new_exe, progress=progress)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        if new_exe.exists():
            try:
                new_exe.unlink()
            except OSError:
                pass
        return False, f"Не удалось скачать обновление:\n{exc}", False

    if new_exe.stat().st_size < 1024 * 1024:
        try:
            new_exe.unlink()
        except OSError:
            pass
        return False, "Скачанный файл обновления повреждён или пуст.", False

    try:
        bat_path = _create_windows_replacer(target_exe, new_exe, os.getpid())
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            cwd=str(install_root()),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except OSError as exc:
        try:
            new_exe.unlink()
        except OSError:
            pass
        return False, f"Не удалось запустить установку обновления:\n{exc}", False

    return True, "Обновление загружено. Приложение перезапустится.", True


def open_download_page() -> None:
    QDesktopServices.openUrl(QUrl(f"{GITHUB_URL}/releases"))


def perform_update(remote_version: str | None = None) -> tuple[bool, str, bool]:
    """Обновить приложение. Возвращает (успех, сообщение, завершить приложение)."""
    if git_source_root() is not None:
        ok, message = run_git_update()
        return ok, message, ok

    if is_frozen_app():
        if not remote_version:
            return False, "Не указана версия обновления.", False
        return run_exe_update(remote_version)

    open_download_page()
    return (
        True,
        "Открыта страница релизов на GitHub.\n"
        f"Скачайте {RELEASE_EXE_NAME} и замените текущий файл.",
        False,
    )


class UpdateCheckThread(QThread):
    finished_check = Signal(object)  # str | None

    def run(self) -> None:
        self.finished_check.emit(fetch_remote_version())


class UpdateInstallThread(QThread):
    progress = Signal(int, int)
    finished_install = Signal(bool, str, bool)

    def __init__(self, remote_version: str, parent=None) -> None:
        super().__init__(parent)
        self._remote_version = remote_version

    def run(self) -> None:
        def report(done: int, total: int) -> None:
            self.progress.emit(done, total)

        ok, message, quit_app = run_exe_update(self._remote_version, progress=report)
        self.finished_install.emit(ok, message, quit_app)


def mark_version_skipped(version: str) -> None:
    skip_update_version(version)
