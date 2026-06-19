"""Проверка и установка обновлений с GitHub."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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
_GITHUB_HOSTS = frozenset({
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})
_DOWNLOAD_RETRIES = 5
_DOWNLOAD_CHUNK = 128 * 1024


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


def _find_exe_asset(release: dict) -> tuple[str | None, int | None]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None, None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") == RELEASE_EXE_NAME:
            url = asset.get("browser_download_url")
            asset_id = asset.get("id")
            safe_url = url if isinstance(url, str) and _is_safe_github_url(url) else None
            safe_id = asset_id if isinstance(asset_id, int) else None
            if safe_url or safe_id:
                return safe_url, safe_id
    return None, None


def _is_safe_github_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in _GITHUB_HOSTS


def fetch_latest_release_version(timeout: float = 15.0) -> str | None:
    """Версия из последнего GitHub Release (для exe и релизных сборок)."""
    latest = _github_get_json(f"{GITHUB_API_BASE}/releases/latest", timeout=timeout)
    if isinstance(latest, dict):
        tag = latest.get("tag_name")
        if isinstance(tag, str) and tag.strip():
            return _release_tag_version(tag)

    releases = _github_get_json(
        f"{GITHUB_API_BASE}/releases?per_page=20", timeout=timeout
    )
    if not isinstance(releases, list):
        return None

    best: tuple[int, ...] | None = None
    best_version: str | None = None
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        if release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag.strip():
            continue
        version = _release_tag_version(tag)
        key = version_tuple(version)
        if best is None or key > best:
            best = key
            best_version = version
    return best_version


def fetch_remote_version(timeout: float = 12.0) -> str | None:
    release_version = fetch_latest_release_version(timeout=timeout)
    if release_version:
        return release_version

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


def fetch_release_download(version: str) -> tuple[str | None, int | None, str]:
    for tag in (f"v{version}", version):
        release = _github_get_json(f"{GITHUB_API_BASE}/releases/tags/{tag}")
        if isinstance(release, dict):
            url, asset_id = _find_exe_asset(release)
            if url or asset_id:
                return url, asset_id, ""

    latest = _github_get_json(f"{GITHUB_API_BASE}/releases/latest")
    if isinstance(latest, dict):
        if _release_tag_version(str(latest.get("tag_name", ""))) == version:
            url, asset_id = _find_exe_asset(latest)
            if url or asset_id:
                return url, asset_id, ""

    return (
        None,
        None,
        f"На GitHub не найден релиз {version} с файлом {RELEASE_EXE_NAME}.\n"
        f"Страница релизов: {GITHUB_URL}/releases",
    )


def fetch_release_exe_url(version: str) -> tuple[str | None, str]:
    url, _asset_id, error = fetch_release_download(version)
    return url, error


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


def _download_headers(range_start: int = 0) -> dict[str, str]:
    headers = {
        "User-Agent": f"DXF-SkyView/{APP_VERSION}",
        "Accept": "application/octet-stream",
    }
    if range_start > 0:
        headers["Range"] = f"bytes={range_start}-"
    return headers


def _parse_download_total(response, range_start: int) -> int:
    content_range = response.headers.get("Content-Range")
    if content_range:
        parts = content_range.split("/")
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1])
    content_length = response.headers.get("Content-Length")
    if content_length and content_length.isdigit():
        return range_start + int(content_length)
    return -1


def _download_http_once(
    url: str,
    destination: Path,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 600.0,
) -> None:
    if not _is_safe_github_url(url):
        raise ValueError("Недопустимый адрес загрузки.")

    range_start = destination.stat().st_size if destination.exists() else 0
    request = urllib.request.Request(url, headers=_download_headers(range_start))
    mode = "ab" if range_start > 0 else "wb"
    destination.parent.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = _parse_download_total(response, range_start)
        received = range_start
        if progress is not None:
            progress(received, total)

        with destination.open(mode) as handle:
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                received += len(chunk)
                if progress is not None:
                    progress(received, total)


def _download_http(
    url: str,
    destination: Path,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 600.0,
) -> None:
    last_error: Exception | None = None
    for attempt in range(_DOWNLOAD_RETRIES):
        try:
            _download_http_once(url, destination, progress=progress, timeout=timeout)
            return
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if destination.exists() and destination.stat().st_size == 0:
                destination.unlink(missing_ok=True)
            time.sleep(min(2**attempt, 12))
    if last_error is not None:
        raise last_error
    raise OSError("Не удалось скачать файл.")


def _download_api_asset(
    asset_id: int,
    destination: Path,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 600.0,
) -> None:
    url = f"{GITHUB_API_BASE}/releases/assets/{asset_id}"
    _download_http(url, destination, progress=progress, timeout=timeout)


def _download_with_curl(
    url: str,
    destination: Path,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise FileNotFoundError("curl не найден в системе.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [
        curl,
        "-L",
        "-f",
        "-s",
        "--retry",
        "8",
        "--retry-delay",
        "2",
        "--retry-all-errors",
        "--connect-timeout",
        "30",
        "--max-time",
        "1800",
        "-A",
        f"DXF-SkyView/{APP_VERSION}",
        "-o",
        str(destination),
    ]
    if destination.exists() and destination.stat().st_size > 0:
        args.extend(["-C", "-"])
    args.append(url)

    proc = subprocess.Popen(args)
    while proc.poll() is None:
        if progress is not None and destination.exists():
            progress(destination.stat().st_size, -1)
        time.sleep(0.4)

    if proc.returncode != 0:
        raise OSError(f"curl завершился с кодом {proc.returncode}")


def _download_file(
    url: str | None,
    destination: Path,
    progress: Callable[[int, int], None] | None = None,
    asset_id: int | None = None,
    timeout: float = 600.0,
) -> None:
    if destination.exists():
        try:
            destination.unlink()
        except OSError:
            pass

    errors: list[str] = []
    methods: list[tuple[str, Callable[[], None]]] = []
    if url:
        methods.append(("HTTP", lambda: _download_http(url, destination, progress, timeout)))
    if asset_id is not None:
        methods.append((
            "GitHub API",
            lambda: _download_api_asset(asset_id, destination, progress, timeout),
        ))
    if sys.platform == "win32" and url:
        methods.append(("curl", lambda: _download_with_curl(url, destination, progress)))

    for name, method in methods:
        if destination.exists():
            try:
                destination.unlink()
            except OSError:
                pass
        try:
            method()
            if destination.is_file() and destination.stat().st_size >= 1024 * 1024:
                return
            errors.append(f"{name}: файл слишком маленький")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            if destination.exists():
                try:
                    destination.unlink()
                except OSError:
                    pass

    details = "\n".join(errors) if errors else "неизвестная ошибка"
    raise OSError(
        "Не удалось скачать обновление.\n"
        f"{details}\n\n"
        "Проверьте интернет, антивирус или VPN.\n"
        f"Можно скачать вручную: {GITHUB_URL}/releases"
    )


def _create_windows_replacer(
    target_exe: Path,
    new_exe: Path,
    pid: int,
) -> Path:
    """PowerShell-скрипт: дождаться выхода процесса, заменить exe, запустить."""
    script_path = Path(tempfile.gettempdir()) / f"skyview_update_{pid}.ps1"
    target = str(target_exe).replace("'", "''")
    new = str(new_exe).replace("'", "''")
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$target = '{target}'",
        f"$new = '{new}'",
        f"$procId = {pid}",
        "$deadline = (Get-Date).AddMinutes(3)",
        "while ((Get-Process -Id $procId -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {",
        "    Start-Sleep -Milliseconds 500",
        "}",
        "for ($i = 0; $i -lt 90; $i++) {",
        "    if (-not (Test-Path -LiteralPath $new)) { exit 1 }",
        "    try {",
        "        if (Test-Path -LiteralPath $target) {",
        "            Remove-Item -LiteralPath $target -Force",
        "        }",
        "        Move-Item -LiteralPath $new -Destination $target -Force",
        "        if (Test-Path -LiteralPath $target) {",
        "            Start-Process -FilePath $target",
        "            Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
        "            exit 0",
        "        }",
        "    } catch {",
        "        Start-Sleep -Seconds 1",
        "    }",
        "}",
        "exit 1",
    ]
    script_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return script_path


def _launch_windows_updater(script_path: Path) -> None:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script_path),
        ],
        cwd=str(install_root()),
        creationflags=creationflags,
        close_fds=True,
    )


def run_exe_update(
    remote_version: str,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[bool, str, bool]:
    """Скачать релиз и подготовить замену exe. Третье значение — завершить приложение."""
    if not is_frozen_app():
        return False, "Автообновление exe доступно только в собранной версии.", False
    if sys.platform != "win32":
        return False, "Автообновление exe поддерживается только в Windows.", False

    download_url, asset_id, error = fetch_release_download(remote_version)
    if not download_url and asset_id is None:
        return False, error, False

    target_exe = Path(sys.executable).resolve()
    new_exe = target_exe.with_name(f"{target_exe.stem}.new.exe")

    if new_exe.exists():
        try:
            new_exe.unlink()
        except OSError:
            return False, "Не удалось подготовить файл обновления.", False

    try:
        _download_file(
            download_url,
            new_exe,
            progress=progress,
            asset_id=asset_id,
        )
    except OSError as exc:
        if new_exe.exists():
            try:
                new_exe.unlink()
            except OSError:
                pass
        return False, str(exc), False

    if new_exe.stat().st_size < 1024 * 1024:
        try:
            new_exe.unlink()
        except OSError:
            pass
        return False, "Скачанный файл обновления повреждён или пуст.", False

    try:
        script_path = _create_windows_replacer(target_exe, new_exe, os.getpid())
        _launch_windows_updater(script_path)
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
