"""Студия, которой эту картину уже смотрели."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState


def _studio_seen(state: WatchState, key: str, found: tuple[str, Entry] | None = None) -> str:
    """Студия, чью озвучку на этой картине уже слушали; пусто - такой памяти нет.

    Ищется так же, как память дорожки (:func:`_remembered`): сперва по каноническому
    ключу картины, а запись, найденную по тексту запроса, берём запасным вариантом -
    один сериал зовут по-разному, а смотрят его одной студией.
    """
    entry = state.get(key) or (found[1] if found is not None else None)
    return entry.studio if entry is not None else ""
