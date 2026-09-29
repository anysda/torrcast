"""Серия за краем раздачи для плашки «Следующая серия»: каталог сериала и пул раздач.

Правило одно с циклом юнита (:func:`torrcast.usecases.series_next.series_next`). Разница в
доказательстве выхода: юнит ищет раздачу сам, а плашка встаёт за 10 с до конца, и искать
ей некогда. Скачок в следующий сезон без даты TVmaze плашка доказывает пулом: у картины
есть раздачи этого сезона в круге поиска (:data:`web.warm_wiring.WARM`). Круг, которого
нет в памяти, греется фоном (:func:`hass.released_seasons.released_seasons`).
"""

from __future__ import annotations

from collections.abc import Callable

from hass.released_seasons import released_seasons
from torrcast.domain.entry import Entry
from torrcast.ports.series_source import AiredState, SeriesSource
from torrcast.usecases.series_next import series_next
from web.series_catalog import SERIES


def catalog_next(
    entry: Entry,
    key: str,
    query: str,
    catalog: SeriesSource = SERIES,
    seasons: Callable[[str, str], tuple[int, ...] | None] = released_seasons,
) -> str | None:
    """Подпись ``s2e1`` серии после ``entry``; ``None`` - сериал кончился или выход не доказан."""
    later = series_next(entry, catalog, lambda: seasons(key, query))
    return f"s{later[0]}e{later[1]}" if later else None


def catalog_waits(entry: Entry, catalog: SeriesSource = SERIES) -> bool:
    """Не ответивший TVmaze оставляет стык юниту, а не объявляет сериал последним."""
    tconst = catalog.ids(entry.title, entry.original, entry.year or None)
    if not tconst:
        return False
    _aired, state = catalog.aired(tconst, 0.0)
    return state is AiredState.UNKNOWN


__all__ = ["catalog_next", "catalog_waits"]
