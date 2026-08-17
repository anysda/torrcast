"""Поле записи ``play/nudge``: сторож расшевелил зависший приёмник.

Зовёт её сам сторож приёмника (:meth:`ChromecastReceiver._nudge`), читает ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def nudge(pos: float, to: float, hit: int, stuck: float, front: float) -> None:
    """Сторож расшевелил зависший приёмник: где стоял, куда прыгнули, каким по счёту.

    ``stuck`` - сколько секунд позиция не двигалась, ``front`` - докуда было упаковано
    (по нему видно, зависание это было или законное ожидание упаковки).
    """
    emit(
        "play",
        "nudge",
        pos=round(pos, 1),
        to=round(to, 1),
        hit=hit,
        stuck=round(stuck, 1),
        front=round(front, 1),
    )
