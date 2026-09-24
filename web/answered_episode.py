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
    """Взять первую ответившую; мёртвую раздачу заменить следующей по отбору."""
    left = [*releases]
    release: Release | None = first
    last = first
    while release is not None:
        table = episodes.table(release, base_url)
        if table is not UNAVAILABLE:
            return table, release
        last = release
        if release not in left:  # раздача закладки вне пула не подменяется соседней
            break
        left.remove(release)
        release = choose(left)
    return UNAVAILABLE, last


def _episodes_unavailable(episodes: object, release: Release | None) -> bool:
    """Прочитать новый приговор, не расширяя старый порт одной ``table()``."""
    check = getattr(episodes, "unavailable", None)
    return bool(check(release)) if callable(check) else False


__all__ = ["answered_episode"]
