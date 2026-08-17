"""Поля записи ``play/reload``: повтор LOAD посреди показа.

Зовут её обе ветки повтора у приёмника, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def reload(pos: float, tries: int, error: int | None = None) -> None:
    """Повтор LOAD посреди показа: приёмник отвалился и его подняли заново."""
    emit("play", "reload", pos=round(pos, 1), tries=tries, error=error)
