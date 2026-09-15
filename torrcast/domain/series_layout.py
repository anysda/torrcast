"""Сезоны и серии сериала из каталога: раскладка, которая сходится с раздачами.

Два источника нумеруют один сериал по-разному. IMDb держит «Интернов» четырьмя сезонами
по 60-98 серий, TVmaze и раздачи - четырнадцатью по 20; «Футураму» русские раздачи зовут
как IMDb, а TVmaze сезоны 6 и 7 сводит в два по 26. Правило одно для всех:

1. берётся раскладка с меньшим числом промахов против имён раздач пула (:func:`_misses`),
   при равенстве - IMDb: она лежит на диске и отвечает без сети;
2. сезон IMDb дорастает до верхнего номера серии односезонной раздачи, если столько серий
   в этом сезоне знает TVmaze: «Футурама» s6 и s7 по 26. Обратного нет: IMDb сводит
   эфирные сезоны в один («Интерны» s1 из 60), и раскладку TVmaze он не раздувает;
3. сезон старше последнего сезона раздач и закладки показывает только серии, которые знает
   TVmaze: пустые заготовки IMDb («Рик и Морти» s10-12 по одной серии) не становятся
   вкладками. Молчит TVmaze - остаются сезоны IMDb;
4. дату серии дают часы TVmaze, если его нумерация сезона совпала с выбранной; серия,
   которая ещё не вышла, несёт дату выхода, вышедшая - пустую строку.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from torrcast.domain.release import Release

#: Серия TVmaze: (сезон, номер) -> (момент выхода ISO для сравнения, дата выхода для глаз).
Aired = Mapping[tuple[int, int], tuple[str, str]]
#: Номера серий по сезонам.
Numbers = Mapping[int, tuple[int, ...]]


def series_layout(
    imdb: Numbers,
    aired: Aired,
    releases: Sequence[Release],
    saved: Iterable[int],
    now: str,
) -> dict[int, list[tuple[int, str]]]:
    """Строки сезонов ``(номер, дата выхода или "")``; пусто - каталог сериала не знает."""
    tvmaze = _by_season(aired)
    candidates = [layout for layout in (imdb, tvmaze) if layout]
    if not candidates:
        return {}
    chosen = min(candidates, key=lambda layout: _misses(layout, releases))
    named = {number for release in releases for number in _named(release)} | set(saved)
    last = max(named, default=None)
    grown = _grown(chosen, tvmaze if chosen is imdb else {}, releases)
    out: dict[int, list[tuple[int, str]]] = {}
    for season in sorted(grown):
        beyond = last is not None and season > last
        if beyond and tvmaze:
            numbers, dated = tvmaze.get(season, ()), True
        else:
            numbers = grown.get(season, ())
            dated = chosen is tvmaze or tvmaze.get(season) == chosen.get(season)
        rows = [
            (number, _coming(aired, season, number, now) if dated else "") for number in numbers
        ]
        if rows:
            out[season] = rows
    return out


def _by_season(aired: Aired) -> dict[int, tuple[int, ...]]:
    seasons: dict[int, list[int]] = {}
    for season, number in sorted(aired):
        seasons.setdefault(season, []).append(number)
    return {season: tuple(numbers) for season, numbers in seasons.items()}


def _named(release: Release) -> tuple[int, ...]:
    if release.seasons:
        return release.seasons
    return (release.season,) if release.season else ()


def _misses(layout: Numbers, releases: Sequence[Release]) -> int:
    """Сколько раздач раскладка не вмещает: нет названного сезона или номера серии.

    Номер серии пака из нескольких сезонов сквозной, поэтому сравнивается с суммой серий
    его сезонов; пак без сезона в имени - с числом всех серий сериала.
    """
    total = sum(len(numbers) for numbers in layout.values())
    return sum(_missed(layout, release, total) for release in releases)


def _missed(layout: Numbers, release: Release, total: int) -> bool:
    seasons = _named(release)
    top = max(release.episodes) if release.episodes else (release.episode or 0)
    if not seasons:
        return bool(top) and (1 not in layout or top > total)
    if any(season not in layout for season in seasons):
        return True
    if len(seasons) == 1:
        return top > max(layout[seasons[0]], default=0)
    return top > sum(len(layout[season]) for season in seasons)


def _grown(
    layout: Numbers, other: Numbers, releases: Sequence[Release]
) -> dict[int, tuple[int, ...]]:
    grown = {season: tuple(numbers) for season, numbers in layout.items()}
    for release in releases:
        season = release.season
        if season in grown and not release.seasons and release.episodes:
            have = max(grown[season], default=0)
            top = max(release.episodes)
            if have < top <= max(other.get(season, ()), default=0):
                grown[season] = (*grown[season], *range(have + 1, top + 1))
    return grown


def _coming(aired: Aired, season: int, number: int, now: str) -> str:
    when, date = aired.get((season, number), ("", ""))
    return date if when > now else ""


__all__ = ["series_layout"]
