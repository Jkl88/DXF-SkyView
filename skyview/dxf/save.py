"""Сохранение изменённого DXF."""

from __future__ import annotations

from skyview.dxf.loader import DxfDocument, EntityRecord


def _entity_for_deletion(record: EntityRecord):
    """Сущность для удаления из файла (для виртуальных — родительский INSERT)."""
    entity = record.entity
    source = getattr(entity, "source", None)
    if source is not None:
        return source
    return entity


def save_dxf(doc: DxfDocument, filepath: str, remaining_records: list[EntityRecord]) -> None:
    """Сохранить DXF, оставив только объекты из remaining_records."""
    remaining_handles = {r.handle for r in remaining_records}
    msp = doc.doc.modelspace()

    to_delete = []
    for record in doc.records:
        if record.handle not in remaining_handles:
            to_delete.append(_entity_for_deletion(record))

    seen = set()
    for entity in to_delete:
        key = entity.dxf.handle
        if key in seen:
            continue
        seen.add(key)
        try:
            msp.delete_entity(entity)
        except (ValueError, KeyError):
            pass

    doc.doc.saveas(filepath)
