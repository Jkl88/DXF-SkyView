"""Единицы измерения из DXF."""

from __future__ import annotations

# Коды $INSUNITS (AutoCAD)
INSUNITS_LABELS: dict[int, str] = {
    0: "unitless",
    1: "in",
    2: "ft",
    3: "mi",
    4: "mm",
    5: "cm",
    6: "m",
    7: "km",
    8: "µin",
    9: "mil",
    10: "yd",
    11: "Å",
    12: "nm",
    13: "µm",
    14: "dm",
    15: "dam",
    16: "hm",
    17: "Gm",
    18: "au",
    19: "ly",
    20: "pc",
}

INSUNITS_SHORT: dict[int, str] = {
    0: "",
    1: "in",
    2: "ft",
    3: "mi",
    4: "mm",
    5: "cm",
    6: "m",
    7: "km",
    8: "µin",
    9: "mil",
    10: "yd",
    11: "Å",
    12: "nm",
    13: "µm",
    14: "dm",
    15: "dam",
    16: "hm",
    17: "Gm",
    18: "au",
    19: "ly",
    20: "pc",
}


def read_units(doc) -> tuple[int, str, str]:
    """Вернуть (код, полное имя, короткую метку) единиц из заголовка DXF."""
    code = int(doc.header.get("$INSUNITS", 0))
    return code, INSUNITS_LABELS.get(code, "unitless"), INSUNITS_SHORT.get(code, "")


def format_length(value: float, unit: str, precision: int = 3) -> str:
    if unit:
        return f"{value:.{precision}f} {unit}"
    return f"{value:.{precision}f}"


def parse_length(text: str, unit: str) -> float | None:
    """Разобрать длину из поля свойств; единица в строке необязательна."""
    raw = text.strip().replace(",", ".")
    if not raw:
        return None
    if unit:
        suffix = f" {unit}"
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].strip()
        elif raw.endswith(unit):
            raw = raw[: -len(unit)].strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value
