"""Сезоны и серии сериала из каталога: раскладка, которая сходится с раздачами.

Два источника нумеруют один сериал по-разному. IMDb держит «Интернов» четырьмя сезонами
по 60-98 серий, TVmaze и раздачи - четырнадцатью по 20; «Футураму» IMDb считает
четырнадцатью сезонами, где шестой - это четыре полнометражных фильма, разрезанные на
16 серий, а TVmaze и раздачи зовут шестым сезоном 26 серий Comedy Central того же года.
Показанная серия должна включаться, поэтому правило одно для всех:

1. показывается раскладка ОДНОГО источника: сложенные вместе, они нумеруют серии, которых
   нет ни у одного. Сезон фильмов IMDb, дорощенный до сезона Comedy Central у TVmaze,
   давал «Футураме» 203 строки на 180 серий, и лишние строки сезонов 8-10 не игрались;
2. берётся раскладка с меньшим числом промахов против имён раздач пула (:func:`_missed`):
   нет названного сезона, номер серии больше сезона, «из N» не равно числу его серий;
   при равенстве - IMDb: она лежит на диске и отвечает без сети;
3. раздачи пула сезона не называют («След [Серии 1-224]»): номера сквозные, и нумерацией
   раздач бывает только раскладка из одного сезона;
4. раскладка не нумерация раздач, если ей противоречит больше половины раздач с номерами
   или молчит TVmaze, а раздачи зовут сезон, которого у IMDb нет. Список она всё равно
   даёт сразу, а серию строки показ ищет по сквозному номеру
   (:class:`torrcast.domain.episode_ordinal.EpisodeOrdinal`), - но только пока она СВОДИТ
   сезоны раздач. Раздача, которая знает в сезонах каталога больше серий, чем он сам
   («Футурама» S1E1-13 против девяти у IMDb), разложила сериал иначе, а не дробнее:
   сквозной номер попал бы в чужую серию, и каталог молчит, оставляя таблицы раздач;
5. сезон старше последнего сезона раздач и закладки показывает только серии, которые знает
   TVmaze, если выбранная раскладка совпала с ним на сезонах раздач: пустые заготовки IMDb
   («Рик и Морти» s10-12 по одной серии) не становятся вкладками;
6. дату серии дают часы TVmaze, если его нумерация сезона совпала с выбранной; серия,
   которая ещё не вышла, несёт дату выхода, вышедшая - пустую строку.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Final

from torrcast.domain.release import Release

#: Серия TVmaze: (сезон, номер) -> (момент выхода ISO для сравнения, дата выхода для глаз).
Aired = Mapping[tuple[int, int], tuple[str, str]]
#: Номера серий по сезонам.
Numbers = Mapping[int, tuple[int, ...]]
#: «Серии: 1-20 из 20», «[S01-03E01-60 of 60]»; «из 1000+» и «из XX» числа не называют.
_OF_RE: Final = re.compile(r"(?<=\d)\s*(?:из|of)\s*(\d{1,4})(?![\d+])", re.IGNORECASE)


def series_layout(
    imdb: Numbers,
    aired: Aired,
    releases: Sequence[Release],
    saved: Iterable[int],
    now: str,
) -> tuple[dict[int, list[tuple[int, str]]], bool]:
    """Строки сезонов ``(номер, дата выхода или "")`` и «это нумерация раздач».

    Пусто - каталог сериала не знает.
    """
    tvmaze = _by_season(aired)
    pooled = {number for release in releases for number in _named(release)}
    candidates: list[Numbers] = [layout for layout in (imdb, tvmaze) if layout]
    single = [layout for layout in candidates if set(layout) == {1}]
    if not candidates:
        return {}, False
    chosen = min(single if single and not pooled else candidates, key=_weigh(releases))
    counted = sum(1 for release in releases if _named(release) or _top(release))
    direct = (bool(pooled) or set(chosen) == {1}) and not (
        2 * _misses(chosen, releases) > counted or (not tvmaze and not pooled <= imdb.keys())
    )
    if not direct and _splits(chosen, releases):
        return {}, False
    named = pooled | set(saved)
    last = max(named, default=None)
    common = [s for s in chosen.keys() & tvmaze.keys() if last is not None and s <= last]
    agrees = bool(tvmaze) and all(chosen[s] == tvmaze[s] for s in common)
    out: dict[int, list[tuple[int, str]]] = {}
    for season in sorted(chosen):
        if last is not None and season > last and agrees:
            numbers, dated = tvmaze.get(season, ()), True
        else:
            numbers, dated = chosen[season], tvmaze.get(season) == chosen[season]
        rows = [
            (number, _coming(aired, season, number, now) if dated else "") for number in numbers
        ]
        if rows:
            out[season] = rows
    return out, direct


def _weigh(releases: Sequence[Release]) -> Callable[[Numbers], int]:
    return lambda layout: _misses(layout, releases)


def _by_season(aired: Aired) -> dict[int, tuple[int, ...]]:
    seasons: dict[int, list[int]] = {}
    for season, number in sorted(aired):
        seasons.setdefault(season, []).append(number)
    return {season: tuple(numbers) for season, numbers in seasons.items()}


def _named(release: Release) -> tuple[int, ...]:
    if release.seasons:
        return release.seasons
    return (release.season,) if release.season else ()


def _top(release: Release) -> int:
    return max(release.episodes) if release.episodes else (release.episode or 0)


def _misses(layout: Numbers, releases: Sequence[Release]) -> int:
    """Сколько раздач раскладка не вмещает: нет сезона, номера серии или числа «из N».

    Номер серии пака из нескольких сезонов сквозной, поэтому сравнивается с суммой серий
    его сезонов; пак без сезона в имени - с числом всех серий сериала.
    """
    total = sum(len(numbers) for numbers in layout.values())
    return sum(_missed(layout, release, total) for release in releases)


def _missed(layout: Numbers, release: Release, total: int) -> bool:
    seasons, top = _named(release), _top(release)
    if not seasons:
        return bool(top) and (1 not in layout or top > total)
    if any(season not in layout for season in seasons):
        return True
    top_held, held = _held(layout, seasons)
    whole = _OF_RE.search(release.raw_name)
    return top > top_held or (whole is not None and int(whole.group(1)) != held)


def _splits(layout: Numbers, releases: Sequence[Release]) -> bool:
    """Раскладка дробит сериал не как раздачи, а по-своему: сквозной номер ей не помощник.

    Признак - раздача, которая называет в сезонах раскладки больше серий, чем та держит
    («Футурама» S1E1-13 из 13 против девяти у IMDb): раздачи не дробят её сезоны, а
    расходятся с ней составом, и N-й файл подряд уже не N-я строка списка.
    """
    for release in releases:
        seasons = _named(release)
        if not seasons or any(season not in layout for season in seasons):
            continue
        top_held, held = _held(layout, seasons)
        whole = _OF_RE.search(release.raw_name)
        if _top(release) > top_held or (whole is not None and int(whole.group(1)) > held):
            return True
    return False


def _held(layout: Numbers, seasons: Sequence[int]) -> tuple[int, int]:
    """Верхний номер серии сезона и сколько серий всего держит раскладка в этих сезонах."""
    held = sum(len(layout[season]) for season in seasons)
    return (max(layout[seasons[0]], default=0) if len(seasons) == 1 else held, held)


def _coming(aired: Aired, season: int, number: int, now: str) -> str:
    when, date = aired.get((season, number), ("", ""))
    return date if when > now else ""


__all__ = ["series_layout"]
