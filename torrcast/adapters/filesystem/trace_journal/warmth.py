"""Поля записей ``warm/ready`` и ``warm/stall``: доля прогретого на этот момент.

Зовёт её прогрев, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def warmth(event: str, secs: float, dur: float, size: int, why: str = "") -> None:
    """Доля прогретого на этот момент: секунды на диске, длина фильма, доля и вес.

    ``event`` - ``ready`` (фильм лёг целиком) или ``stall`` (прогрев встал, причина - в
    ``why``). Доля считается здесь, чтобы читатель ленты её не пересчитывал.
    """
    emit(
        "warm",
        event,
        secs=round(secs),
        dur=round(dur),
        share=round(secs / dur, 3) if dur > 0 else 0.0,
        size=size,
        why=why,
    )
