"""Поля записи ``warm/evict``: прогрев вытеснил каталог, который держал место.

Зовут её бюджет прогрева и сборщик полок прежних форм ключа
(:func:`torrcast.usecases.warm.strip_forms.strip_forms`), читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def evict(key: str, freed: int, need: int, title: str = "") -> None:
    """Прогрев вытеснил каталог: кого, сколько байт освободил и подо что."""
    emit("warm", "evict", key=key, title=title, freed=freed, need=need)
