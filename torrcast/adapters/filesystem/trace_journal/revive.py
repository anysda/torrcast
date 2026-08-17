"""Поля записи ``play/revive``: попытка поднять погасший показ.

Зовёт её воскрешение показа, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def revive(pos: float, tries: int, waited: float, ok: bool) -> None:
    """Попытка поднять погасший показ: откуда, какая по счёту, после скольких секунд темноты.

    ``ok`` - взял ли приёмник LOAD. Ложь тут не хуже правды: по ней и видно, сколько раз
    воскрешение не удалось, прежде чем показ погас честно.
    """
    emit("play", "revive", pos=round(pos, 1), tries=tries, waited=round(waited, 1), ok=ok)
