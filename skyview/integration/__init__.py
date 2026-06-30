"""Интеграция с внешними программами."""

from skyview.integration.file_association import (
    deploy_file_icon,
    is_dxf_associated,
    is_dwg_associated,
    register_dxf_association,
    unregister_dxf_association,
)
from skyview.integration.rectangle_creator import (
    get_installation_info,
    import_dxf,
    is_rectangle_creator_available,
)

__all__ = [
    "deploy_file_icon",
    "get_installation_info",
    "import_dxf",
    "is_dxf_associated",
    "is_dwg_associated",
    "is_rectangle_creator_available",
    "register_dxf_association",
    "unregister_dxf_association",
]