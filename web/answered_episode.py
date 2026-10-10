"""Первая ответившая таблица серий в порядке отбора раздач."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from torrcast.domain.release import Release
from web.episode_lookup import UNAVAILABLE


class _EpisodeTables(Protocol):
    """Кэш таблиц серий, достаточный карточке."""

    def table(self, release: Release, base_url: str) -> list[list[int]] | None: ...


_Choose = Callable[[list[Release]], Release | None]


def answered_episode(
    releases: list[Release],
    episodes: _EpisodeTables,
    base_url: str,
    choose: _Choose,
    first: Release,
) -> tuple[list[list[int]] | None, Release]:
    """Взять первую ответившую; мёртвую раздачу заменить следующей по отбору.

    Раздача, в файлах которой показ не находит ни одной серии («S1-4» с файлами «1ACV01»),
    для строк карточки так же пуста, как мёртвая: показ её пропустит и сыграет следующую,
    значит и строки рисует следующая. Пустые все - честная пустая таблица первой из них.
    """
    left = [*releases]
    release: Release | None = first
    last = first
    empty: tuple[list[list[int]], Release] | None = None
    while release is not None:
        table = episodes.table(release, base_url)
        if table is None or (table is not UNAVAILABLE and table):
            return table, release
        if table is not UNAVAILABLE and empty is None:
            empty = table, release
        last = release
        if release not in left:  # раздача закладки вне пула не подменяется соседней
            break
        left.remove(release)
        release = choose(left)
    return empty if empty is not None else (UNAVAILABLE, last)


def _episodes_unavailable(episodes: object, release: Release | None) -> bool:
    """Прочитать новый приговор, не расширяя старый порт одной ``table()``."""
    check = getattr(episodes, "unavailable", None)
    return bool(check(release)) if callable(check) else False


__all__ = ["answered_episode"]
