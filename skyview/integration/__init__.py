"""Интеграция с внешними программами."""

from skyview.integration.rectangle_creator import (
    get_installation_info,
    import_dxf,
    is_rectangle_creator_available,
)

__all__ = [
    "get_installation_info",
    "import_dxf",
    "is_rectangle_creator_available",
]
