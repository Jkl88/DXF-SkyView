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


def _update_cache_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "DXF-SkyView" / "updates"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _update_download_path(version: str) -> Path:
    safe = re.sub(r'[<>:"/\\|?*]+', "_", version.strip()) or "latest"
    return _update_cache_dir() / f"DXF-SkyView-{safe}.exe"


def _safe_unlink(path: Path, *, retries: int = 8) -> bool:
    if not path.exists():
        return True
    for attempt in range(retries):
        try:
            path.unlink()
            return True
        except OSError:
            time.sleep(0.35 * (attempt + 1))
    return False


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


APPLY_UPDATE_FLAG = "--apply-update"


def _windows_detached_flags() -> int:
    flags = subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"):
        flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    return flags


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_for_process_exit(pid: int, timeout_sec: float = 180.0) -> None:
    deadline = time.time() + timeout_sec
    while _process_exists(pid) and time.time() < deadline:
        time.sleep(0.4)
    time.sleep(1.5)


def _start_detached(exe_path: Path) -> None:
    subprocess.Popen(
        [str(exe_path)],
        cwd=str(exe_path.parent),
        creationflags=_windows_detached_flags(),
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _shell_execute_error_message(code: int) -> str:
    messages = {
        0: "Недостаточно памяти для запуска установщика.",
        2: "Файл установщика не найден.",
        3: "Путь к установщику не найден.",
        5: "Отказано в доступе.",
        1223: "Обновление отменено: не получены права администратора.",
    }
    return messages.get(code, f"Не удалось запустить установщик (код {code}).")


def _launch_elevated(exe: Path, parameters: str, parent_hwnd: int | None = None) -> None:
    """Запуск с запросом UAC (нужно для установки в Program Files)."""
    import ctypes

    exe = exe.resolve()
    hwnd = int(parent_hwnd) if parent_hwnd else 0
    result = ctypes.windll.shell32.ShellExecuteW(
        hwnd,
        "runas",
        str(exe),
        parameters,
        str(exe.parent),
        1,  # SW_SHOWNORMAL — окно UAC должно быть видно
    )
    if result <= 32:
        raise OSError(_shell_execute_error_message(result))


def _launch_elevated_powershell(exe: Path, parameters: str) -> None:
    """Резервный запуск через PowerShell -Verb RunAs."""
    exe = exe.resolve()
    parts = parameters.split()
    arg_list = ",".join(f"'{part}'" for part in parts)
    ps_cmd = (
        f"Start-Process -LiteralPath '{exe}' -ArgumentList {arg_list} "
        "-Verb RunAs -WindowStyle Hidden"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_cmd,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise OSError(
            "Не удалось запросить права администратора.\n"
            + (detail if detail else f"код {result.returncode}")
        )


def _launch_silent_setup(setup_exe: Path, parent_hwnd: int | None = None) -> None:
    """Тихая установка обновления (Inno Setup) с правами администратора."""
    params = "/VERYSILENT /SUPPRESSMSGBOXES /CLOSEAPPLICATIONS /MERGETASKS=associate"
    try:
        _launch_elevated(setup_exe, params, parent_hwnd)
    except OSError:
        _launch_elevated_powershell(setup_exe, params)


def _is_inno_installer(path: Path) -> bool:
    """Inno Setup: подпись в начале файла (не только в первых 512 КБ)."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            probe = handle.read(min(size, 8 * 1024 * 1024))
        if b"Inno Setup" in probe:
            return True
        # Установщик ~40+ МБ, приложение в Program Files — несколько МБ.
        if size >= 20 * 1024 * 1024:
            return True
    except OSError:
        pass
    return False


def _launch_apply_update(new_exe: Path, target_exe: Path, parent_pid: int) -> None:
    """Запустить скачанный exe в режиме замены (отдельное дерево процессов)."""
    args = [
        str(new_exe),
        APPLY_UPDATE_FLAG,
        str(target_exe),
        str(parent_pid),
    ]
    subprocess.Popen(
        args,
        cwd=str(install_root()),
        creationflags=_windows_detached_flags(),
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def apply_downloaded_update(target_exe: Path, parent_pid: int) -> int:
    """Режим --apply-update: дождаться выхода старого процесса и установить обновление."""
    source_exe = Path(sys.executable).resolve()
    target_exe = target_exe.resolve()
    log_path = Path(tempfile.gettempdir()) / f"skyview_update_{parent_pid}.log"

    def log(message: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] {message}\n")
        except OSError:
            pass

    log(f"apply-update started source={source_exe} target={target_exe} pid={parent_pid}")
    _wait_for_process_exit(parent_pid)

    min_size = 1024 * 1024
    if not source_exe.is_file() or source_exe.stat().st_size < min_size:
        log("source exe missing or too small")
        return 1

    for attempt in range(120):
        try:
            if target_exe.exists():
                target_exe.unlink()
        except OSError as exc:
            log(f"delete attempt {attempt + 1}: {exc}")
            time.sleep(1)
            continue

        try:
            shutil.copy2(source_exe, target_exe)
        except OSError as exc:
            log(f"copy attempt {attempt + 1}: {exc}")
            time.sleep(1)
            continue

        if target_exe.is_file() and target_exe.stat().st_size >= min_size:
            log("copy ok, launching updated exe")
            _start_detached(target_exe)
            return 0

        log(f"copy attempt {attempt + 1}: target invalid after copy")
        time.sleep(1)

    log("failed after retries")
    return 1


def cleanup_stale_new_exe() -> None:
    """Удалить остатки неудачных portable-обновлений (не трогать кэш установщика)."""
    if not is_frozen_app() or sys.platform != "win32":
        return
    target_exe = Path(sys.executable).resolve()
    stale_new = target_exe.with_name(f"{target_exe.stem}.new.exe")
    if stale_new != target_exe:
        _safe_unlink(stale_new)
    _safe_unlink(Path(tempfile.gettempdir()) / RELEASE_EXE_NAME)


def download_exe_update(
    remote_version: str,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[bool, str, Path | None]:
    """Скачать обновление. Запуск установки — на UI-потоке (для UAC)."""
    if not is_frozen_app():
        return False, "Автообновление exe доступно только в собранной версии.", None
    if sys.platform != "win32":
        return False, "Автообновление exe поддерживается только в Windows.", None

    download_url, asset_id, error = fetch_release_download(remote_version)
    if not download_url and asset_id is None:
        return False, error, None

    new_exe = _update_download_path(remote_version)

    if not _safe_unlink(new_exe):
        fallback = new_exe.with_name(
            f"{new_exe.stem}-{int(time.time())}{new_exe.suffix}"
        )
        if _safe_unlink(fallback):
            new_exe = fallback
        else:
            return (
                False,
                "Не удалось подготовить файл обновления.\n"
                f"Не удаётся очистить папку:\n{new_exe.parent}\n\n"
                "Закройте другие копии программы и повторите попытку.",
                None,
            )

    try:
        _download_file(
            download_url,
            new_exe,
            progress=progress,
            asset_id=asset_id,
        )
    except OSError as exc:
        if new_exe.exists():
            _safe_unlink(new_exe)
        return False, str(exc), None

    if new_exe.stat().st_size < 512 * 1024:
        _safe_unlink(new_exe)
        return False, "Скачанный файл обновления повреждён или пуст.", None

    return True, "", new_exe


def apply_downloaded_release(
    installer_path: Path,
    parent_hwnd: int | None = None,
) -> tuple[bool, str]:
    """Запустить скачанное обновление (с UI-потока, с запросом UAC)."""
    installer_path = Path(installer_path).resolve()
    if not installer_path.is_file():
        return False, f"Файл обновления не найден:\n{installer_path}"

    target_exe = Path(sys.executable).resolve()
    legacy_new = target_exe.with_name(f"{target_exe.stem}.new.exe")

    try:
        if _is_inno_installer(installer_path):
            _launch_silent_setup(installer_path, parent_hwnd)
        else:
            if legacy_new.exists() and not _safe_unlink(legacy_new):
                return (
                    False,
                    "Не удалось подготовить файл обновления в папке программы.\n"
                    f"{legacy_new.parent}\n\n"
                    "Запустите программу от имени администратора или обновите вручную.",
                )
            shutil.copy2(installer_path, legacy_new)
            _launch_apply_update(legacy_new, target_exe, os.getpid())
    except OSError as exc:
        return False, f"Не удалось запустить установку обновления:\n{exc}"

    return True, "Обновление загружено. Приложение перезапустится."


def run_exe_update(
    remote_version: str,
    progress: Callable[[int, int], None] | None = None,
    parent_hwnd: int | None = None,
) -> tuple[bool, str, bool]:
    """Скачать и установить обновление (parent_hwnd — для UAC на UI-потоке)."""
    ok, message, installer_path = download_exe_update(remote_version, progress=progress)
    if not ok:
        return False, message, False
    if installer_path is None:
        return False, "Файл обновления не получен.", False

    ok, message = apply_downloaded_release(installer_path, parent_hwnd)
    if not ok:
        _safe_unlink(installer_path)
        return False, message, False

    return True, message, True


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
    finished_install = Signal(bool, str, object)  # str path | None

    def __init__(self, remote_version: str, parent=None) -> None:
        super().__init__(parent)
        self._remote_version = remote_version

    def run(self) -> None:
        def report(done: int, total: int) -> None:
            self.progress.emit(done, total)

        ok, message, installer_path = download_exe_update(
            self._remote_version, progress=report
        )
        path_value = str(installer_path) if ok and installer_path is not None else None
        self.finished_install.emit(ok, message, path_value)


def mark_version_skipped(version: str) -> None:
    skip_update_version(version)
