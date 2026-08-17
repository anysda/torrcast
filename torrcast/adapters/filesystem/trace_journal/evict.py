"""Поля записи ``warm/evict``: бюджет прогрева вытеснил чужой каталог.

Зовёт её бюджет прогрева, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def evict(key: str, freed: int, need: int, title: str = "") -> None:
    """Бюджет прогрева вытеснил чужой каталог: кого, сколько байт освободил и подо что."""
    emit("warm", "evict", key=key, title=title, freed=freed, need=need)
