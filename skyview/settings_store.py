"""Сохранение настроек между запусками."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings

from skyview.tools.snap import DEFAULT_SNAP_PRIORITY, SnapMode


THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_MODES = frozenset({THEME_SYSTEM, THEME_LIGHT, THEME_DARK})


def _settings() -> QSettings:
    return QSettings()


def load_theme_mode() -> str:
    value = _settings().value("ui/theme", THEME_SYSTEM)
    if isinstance(value, str) and value in THEME_MODES:
        return value
    return THEME_SYSTEM


def save_theme_mode(mode: str) -> None:
    if mode in THEME_MODES:
        _settings().setValue("ui/theme", mode)


def last_open_dir() -> str:
    value = _settings().value("paths/lastOpenDir", "")
    if isinstance(value, str) and value and os.path.isdir(value):
        return value
    return ""


def set_last_open_dir(filepath: str) -> None:
    folder = os.path.dirname(os.path.abspath(filepath))
    if os.path.isdir(folder):
        _settings().setValue("paths/lastOpenDir", folder)


def load_snap_priority() -> list[SnapMode]:
    raw = _settings().value("snap/priority")
    if not raw:
        return list(DEFAULT_SNAP_PRIORITY)
    names = raw if isinstance(raw, list) else [raw]
    result: list[SnapMode] = []
    known = {m.name for m in SnapMode}
    for name in names:
        if name in known:
            mode = SnapMode[name]
            if mode not in result:
                result.append(mode)
    for mode in DEFAULT_SNAP_PRIORITY:
        if mode not in result:
            result.append(mode)
    return result


def save_snap_priority(priority: list[SnapMode]) -> None:
    _settings().setValue("snap/priority", [m.name for m in priority])


def load_snap_enabled() -> dict[SnapMode, bool] | None:
    raw = _settings().value("snap/enabled")
    if not raw or not isinstance(raw, dict):
        return None
    result: dict[SnapMode, bool] = {}
    for name, enabled in raw.items():
        if name in SnapMode.__members__:
            result[SnapMode[name]] = bool(enabled)
    return result or None


def save_snap_enabled(enabled: dict[SnapMode, bool]) -> None:
    _settings().setValue("snap/enabled", {m.name: v for m, v in enabled.items()})


def load_skipped_update_versions() -> set[str]:
    raw = _settings().value("update/skippedVersions")
    if not raw:
        return set()
    names = raw if isinstance(raw, list) else [raw]
    return {str(v) for v in names if v}


def skip_update_version(version: str) -> None:
    skipped = load_skipped_update_versions()
    skipped.add(version)
    _settings().setValue("update/skippedVersions", sorted(skipped))
