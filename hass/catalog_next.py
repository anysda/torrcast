"""Серия за краем раздачи: раздача кончилась, а сериал идёт дальше.

Раздача одной серии или одного сезона соседей своей последней серии не знает
(:meth:`torrcast.domain.entry.Entry.advance` отвечает «досмотрено»), а сериал знает
каталог - тот же, по которому карточка раскладывает сезоны (:data:`web.series_catalog.SERIES`).
Следующая - ближайшая серия после этой: дальше в её сезоне, иначе первая серия следующего.

Каталог TVmaze нумерует сериал так, как его раскладывают раздачи, и знает даты выхода:
серия, которой ещё нет в эфире, следующей не считается, иначе плашка обещала бы то, чего
нет ни на одной раздаче. Без ответа TVmaze остаётся индекс IMDb. Серия, которой нет в
каталоге (своя нумерация раздачи), соседей в нём не ищет: ответ был бы угадан.
"""

from __future__ import annotations

from torrcast.domain.entry import Entry
from web.series_catalog import SERIES, SeriesCatalog


def catalog_next(entry: Entry, catalog: SeriesCatalog = SERIES) -> str | None:
    """Подпись ``s2e1`` серии после ``entry``; ``None`` - сериал кончился или каталог молчит."""
    if entry.kind != "tv" or entry.season is None or entry.episode is None:
        return None
    tconst = catalog.ids(entry.title, entry.original, entry.year or None)
    if not tconst:
        return None
    aired, _pending = catalog.aired(tconst, 0.0)
    if aired:
        now = catalog.now()
        known = {key for key, (moment, _day) in aired.items() if moment and moment <= now}
    else:
        numbers = catalog.numbers(tconst) or {}
        known = {(season, n) for season, ns in numbers.items() for n in ns}
    here = (entry.season, entry.episode)
    if here not in known:
        return None
    later = sorted(key for key in known if key > here)
    return f"s{later[0][0]}e{later[0][1]}" if later else None


__all__ = ["catalog_next"]
