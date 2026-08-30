"""Поля записи ``play/refetch``: перезабор куска посреди показа и чем он кончился.

Пишет её сухой приёмник, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def refetch(pos: float, tries: int, ok: bool, why: str = "") -> None:
    """Перезабор куска внутри терпения: приёмник поднимал себя сам, не гася показ."""
    emit("play", "refetch", pos=round(pos, 1), tries=tries, ok=ok, why=why)
