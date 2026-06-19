"""Откат действий (удаление)."""

from __future__ import annotations

from dataclasses import dataclass, field

from skyview.dxf.loader import EntityRecord


@dataclass
class DeleteAction:
    records: list[EntityRecord] = field(default_factory=list)


class UndoStack:
    def __init__(self, limit: int = 50):
        self._stack: list[DeleteAction] = []
        self._limit = limit

    def clear(self) -> None:
        self._stack.clear()

    def push_delete(self, records: list[EntityRecord]) -> None:
        if not records:
            return
        self._stack.append(DeleteAction(records=list(records)))
        if len(self._stack) > self._limit:
            self._stack.pop(0)

    def can_undo(self) -> bool:
        return bool(self._stack)

    def pop_undo(self) -> DeleteAction | None:
        if not self._stack:
            return None
        return self._stack.pop()
