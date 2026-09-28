"""Серия за краем раздачи: раздача кончилась, а сериал идёт дальше.

Раздача одной серии или одного сезона соседей своей последней серии не знает
(:meth:`torrcast.domain.entry.Entry.advance` отвечает «досмотрено»), а сериал знает
каталог: IMDb-id по карте имён, номера серий по индексу IMDb, даты выхода по TVmaze.
Следующая - ближайшая серия после этой: дальше в её сезоне, иначе первая серия следующего.

Следующей называется только серия, про которую доказано, что она вышла. Дата TVmaze это
доказывает. Без неё индекс IMDb знает и анонсы («Рик и Морти» s10 при вышедшем s9), и
тогда серия того же сезона годится (сезон уже есть в раздачах, его и играют), а скачок в
следующий сезон - только если раздачи того сезона видел пул (``released``). Серия, которой
нет в каталоге (своя нумерация раздачи), соседей в нём не ищет: ответ был бы угадан.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

from torrcast.domain.entry import Entry
from torrcast.ports.series_source import SeriesSource


def series_next(
    entry: Entry,
    catalog: SeriesSource,
    released: Callable[[], Collection[int] | None] | None = None,
) -> tuple[int, int] | None:
    """Сезон и серия после ``entry``; ``None`` - сериал кончился или выход не доказан.

    ``released`` - сезоны, у которых пул видел раздачи; ``None`` вместо него - тот, кто
    спрашивает, доказывает выход сам, поиском раздачи (цикл юнита).
    """
    if entry.kind != "tv" or entry.season is None or entry.episode is None:
        return None
    tconst = catalog.ids(entry.title, entry.original, entry.year or None)
    if not tconst:
        return None
    aired, _pending = catalog.aired(tconst, 0.0)
    dated = bool(aired)
    if dated:
        now = catalog.now()
        known = {key for key, (moment, _day) in aired.items() if moment and moment <= now}
    else:
        numbers = catalog.numbers(tconst) or {}
        known = {(season, n) for season, ns in numbers.items() for n in ns}
    here = (entry.season, entry.episode)
    if here not in known:
        return None
    later = min((key for key in known if key > here), default=None)
    if later is None or dated or later[0] == entry.season or released is None:
        return later
    return later if later[0] in (released() or ()) else None


__all__ = ["series_next"]
