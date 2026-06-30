#!/usr/bin/env python3
"""Скачать и распаковать ODA File Converter для встраивания в сборку."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ODA_DIR = ROOT / "third_party" / "oda"
DOWNLOAD_DIR = ODA_DIR / "download"
BUNDLE_DIR = ODA_DIR / "ODAFileConverter"
ODA_EXE = BUNDLE_DIR / "ODAFileConverter.exe"
WINGET_ID = "ODA.ODAFileConverter"


def _run(cmd: list[str], **kwargs) -> None:
    print(">", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def _find_msi() -> Path | None:
    if not DOWNLOAD_DIR.is_dir():
        return None
    candidates = sorted(DOWNLOAD_DIR.glob("ODAFileConverter*.msi"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def download_msi() -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    msi = _find_msi()
    if msi is not None and msi.stat().st_size > 1_000_000:
        print(f"MSI уже есть: {msi}")
        return msi

    winget = shutil.which("winget")
    if winget is None:
        raise RuntimeError(
            "winget не найден. Установите ODA File Converter вручную или установите winget."
        )

    _run(
        [
            winget,
            "download",
            "-e",
            "--id",
            WINGET_ID,
            "--accept-package-agreements",
            "--accept-source-agreements",
            "-d",
            str(DOWNLOAD_DIR),
        ]
    )
    msi = _find_msi()
    if msi is None:
        raise RuntimeError(f"MSI не найден в {DOWNLOAD_DIR}")
    return msi


def extract_msi(msi: Path) -> Path:
    extract_dir = ODA_DIR / "_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    _run(
        [
            "msiexec",
            "/a",
            str(msi),
            f"TARGETDIR={extract_dir}",
            "/qn",
        ]
    )

    exe = extract_dir / "ODAFileConverter.exe"
    if not exe.is_file():
        matches = list(extract_dir.rglob("ODAFileConverter.exe"))
        if not matches:
            raise RuntimeError(f"ODAFileConverter.exe не найден после распаковки {msi}")
        exe = matches[0]

    source_dir = exe.parent
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    shutil.copytree(source_dir, BUNDLE_DIR, ignore=shutil.ignore_patterns("*.msi"))

    shutil.rmtree(extract_dir, ignore_errors=True)
    return BUNDLE_DIR


def ensure_oda_converter(*, force: bool = False) -> Path:
    if not force and ODA_EXE.is_file():
        print(f"ODA File Converter готов: {ODA_EXE}")
        return BUNDLE_DIR

    if sys.platform != "win32":
        raise RuntimeError("ODA File Converter встраивается только в Windows-сборку.")

    msi = download_msi()
    extract_msi(msi)
    if not ODA_EXE.is_file():
        raise RuntimeError(f"Не найден {ODA_EXE}")
    print(f"Готово: {BUNDLE_DIR}")
    return BUNDLE_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Перекачать и распаковать заново")
    args = parser.parse_args()
    try:
        ensure_oda_converter(force=args.force)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Ошибка: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
