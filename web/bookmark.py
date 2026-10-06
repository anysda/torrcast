"""Закладка карточки: какую раздачу и серию продолжит «Играть»."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.magnet_hash import magnet_hash


def bookmark(live: Entry | None) -> tuple[str, str]:
    """Раздача и серия, которые продолжит «Играть»; пусто - закладка не ответит.

    Условие то же, что у показа (:func:`torrcast.usecases.cast_command._bookmark.
    _continue_picked`): фильм - начатый и не досмотренный, сериал - любое место до конца.
    """
    if live is None or live.done or not live.magnet or not (live.serial or live.resumable):
        return "", ""
    return magnet_hash(live.magnet), live.label


__all__ = ["bookmark"]
