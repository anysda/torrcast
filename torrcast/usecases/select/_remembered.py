"""Озвучка, которую человек уже выбирал для этой картины."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState


def _remembered(state: WatchState, key: str, found: tuple[str, Entry] | None) -> str:
    """Озвучка, которую пользователь выбирал для этой картины.

    Смотрим по каноническому ключу картины — под ним показ и пишет запись. Запись,
    найденную по тексту запроса (:meth:`State.find`), берём запасным вариантом: у
    одной картины в состоянии могут лежать записи разных запросов («moana» и «моана»),
    и память озвучки не должна зависеть от того, как её позвали в прошлый раз.
    """
    entry = state.get(key) or (found[1] if found is not None else None)
    return entry.voice if entry is not None else ""
