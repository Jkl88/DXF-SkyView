#!/usr/bin/env python3
"""Релиз DXF SkyView: ветка v{APP_VERSION} → сборка → GitHub Release (latest)."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "skyview" / "version.py"
SETUP_EXE = ROOT / "dist" / "DXF-SkyView.exe"
BUILD_SCRIPT = ROOT / "scripts" / "build_installer.py"


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(">", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )


def read_app_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    if not match:
        raise RuntimeError(f"Не найден APP_VERSION в {VERSION_FILE}")
    return match.group(1)


def read_release_exe_name() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'RELEASE_EXE_NAME\s*=\s*["\']([^"\']+)["\']', text)
    return match.group(1) if match else SETUP_EXE.name


def _require_tool(name: str) -> None:
    result = subprocess.run(
        [name, "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Не найден {name} в PATH.")


def _git_porcelain() -> str:
    result = _run(["git", "status", "--porcelain"], capture=True)
    return (result.stdout or "").strip()


def _release_exists(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", "Jkl88/DXF-SkyView"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def commit_if_dirty(message: str) -> bool:
    if not _git_porcelain():
        return False
    _run(["git", "add", "-A"])
    _run(["git", "commit", "-m", message])
    return True


def push_version_branch(branch: str) -> None:
    _run(["git", "checkout", "-B", branch])
    _run(["git", "push", "-u", "origin", f"refs/heads/{branch}:refs/heads/{branch}"])


def build_installer() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Сборка установщика поддерживается только на Windows.")
    _run([sys.executable, str(BUILD_SCRIPT)])
    if not SETUP_EXE.is_file():
        raise RuntimeError(f"Установщик не найден: {SETUP_EXE}")


def publish_release(tag: str, version: str, asset_name: str) -> None:
    notes = (
        f"DXF SkyView {version}\n\n"
        f"Скачайте `{asset_name}` и запустите установку.\n"
        f"Обновление из программы подхватит этот релиз автоматически."
    )
    setup = str(SETUP_EXE)

    if _release_exists(tag):
        print(f"Релиз {tag} уже есть — обновляю файл и помечаю latest.")
        _run(["gh", "release", "upload", tag, setup, "--clobber"])
        _run(["gh", "release", "edit", tag, "--latest", "--title", tag, "--notes", notes])
    else:
        _run(
            [
                "gh",
                "release",
                "create",
                tag,
                setup,
                "--title",
                tag,
                "--latest",
                "--notes",
                notes,
            ]
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push ветки v{APP_VERSION}, сборка установщика, GitHub Release (latest)."
    )
    parser.add_argument(
        "-m",
        "--message",
        help="Сообщение коммита (если есть незакоммиченные изменения)",
    )
    parser.add_argument("--skip-push", action="store_true", help="Не пушить ветку")
    parser.add_argument("--skip-build", action="store_true", help="Не собирать установщик")
    parser.add_argument("--skip-release", action="store_true", help="Не публиковать на GitHub")
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Не коммитить изменения (ошибка, если рабочая копия грязная)",
    )
    return parser.parse_args()


def main() -> int:
    if not (ROOT / ".git").is_dir():
        print("Ошибка: это не git-репозиторий.")
        return 1

    args = parse_args()

    try:
        _require_tool("git")
        if not args.skip_release:
            _require_tool("gh")

        version = read_app_version()
        tag = branch = f"v{version}"
        asset_name = read_release_exe_name()

        print(f"Версия: {version}")
        print(f"Ветка / тег: {tag}")

        dirty = bool(_git_porcelain())
        if dirty:
            if args.no_commit:
                print("Ошибка: есть незакоммиченные изменения. Закоммитьте или уберите --no-commit.")
                return 1
            message = args.message or f"Release {tag}: DXF SkyView {version}."
            if commit_if_dirty(message):
                print("Изменения закоммичены.")

        if not args.skip_push:
            push_version_branch(branch)
            print(f"Ветка запушена: origin/{branch}")

        if not args.skip_build:
            print("Сборка установщика...")
            build_installer()
            size_mb = SETUP_EXE.stat().st_size / (1024 * 1024)
            print(f"Установщик: {SETUP_EXE} ({size_mb:.1f} МБ)")

        if not args.skip_release:
            print("Публикация GitHub Release...")
            publish_release(tag, version, asset_name)

    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Ошибка: {exc}")
        return 1

    print()
    print("Готово.")
    print(f"  Ветка:  https://github.com/Jkl88/DXF-SkyView/tree/{tag}")
    print(f"  Релиз:  https://github.com/Jkl88/DXF-SkyView/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
