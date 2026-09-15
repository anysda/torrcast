"""Номера серий внутри сезона, когда файлы считают их иначе.

Два живых вида: «S01/101 Pilot» (сотни - сезон, как «103/113» у Sonarr) и «Сезон №3. Серия
№041-060» (сквозной счёт через весь сериал, разложенный по сезонам). Зритель и список
серий карточки называют серию местом в сезоне, поэтому оба пересчитываются к нему.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from torrcast.domain.episode_file import EpisodeFile

__all__ = ["season_numbering"]


def season_numbering(
    found: list[EpisodeFile], folders: Mapping[int, int | None]
) -> list[EpisodeFile]:
    """Пересчитать номера к месту в сезоне; ``folders`` - сезон каталога по индексу файла."""
    seasons: dict[int, list[EpisodeFile]] = {}
    for item in found:
        seasons.setdefault(item.season, []).append(item)
    split = [
        item
        for season, items in seasons.items()
        for item in _split_hundreds(season, sorted(items, key=lambda f: f.episode), folders)
    ]
    return sorted(_restart_running(split), key=lambda f: (f.season, f.episode))


def _split_hundreds(
    season: int, items: list[EpisodeFile], folders: Mapping[int, int | None]
) -> list[EpisodeFile]:
    """Сотни сходятся с сезоном КАТАЛОГА у всех файлов: сквозные 101-150 аниме без папки
    сезона остаются сквозными."""
    rests = {f.episode % 100 for f in items}
    if 0 in rests or len(rests) != len(items):
        return items
    if all(folders.get(f.index) == season and f.episode // 100 == season for f in items):
        return [replace(f, episode=f.episode % 100) for f in items]
    return items


def _restart_running(items: list[EpisodeFile]) -> list[EpisodeFile]:
    """Сквозной счёт по сезонам: каждый сезон подряд и начинается сразу за предыдущим.

    Цепочка обязана быть целой от первой серии: у одного сезона «41-60» без соседей
    не узнать, где он начался, и такой пак остаётся как есть.
    """
    seasons: dict[int, list[int]] = {}
    for item in items:
        seasons.setdefault(item.season, []).append(item.episode)
    if len(seasons) < 2:
        return items
    starts: dict[int, int] = {}
    expected = 1
    for season in sorted(seasons):
        numbers = sorted(seasons[season])
        if numbers != list(range(numbers[0], numbers[0] + len(numbers))) or numbers[0] != expected:
            return items
        starts[season] = numbers[0]
        expected = numbers[-1] + 1
    return [replace(f, episode=f.episode - starts[f.season] + 1) for f in items]
