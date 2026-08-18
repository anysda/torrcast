"""Повод сезонного круга: сериал найден, а раздач нужного сезона в нём нет."""

from __future__ import annotations

from tests.usecases.reinforce.stand import franchise, row
from torrcast.domain.args import Args
from torrcast.usecases.reinforce._lacks_season import _lacks_season


def test_a_series_without_the_asked_season_asks_for_one_more_circle() -> None:
    """Живой случай: сезон-пак лежит под ``Angel S01``, и русское слово до него не достаёт."""
    found = franchise("ангел", [row("Ангел / Angel S05 1080p", "a")])

    assert _lacks_season(found, Args(query=["ангел", "s01e01"]))


def test_the_season_in_the_pool_leaves_the_circle_unpaid() -> None:
    """Раздача сезон нужного сезона называет сама - лишнего круга по индексерам нет."""
    found = franchise("ангел", [row("Ангел / Angel S01 1080p", "b")])

    assert not _lacks_season(found, Args(query=["ангел", "s01e01"]))


def test_the_first_season_is_the_default_want() -> None:
    """Серию не назвали - спрошен первый сезон, и его отсутствие тоже повод."""
    found = franchise("ангел", [row("Ангел / Angel S03 1080p", "c")])

    assert _lacks_season(found, Args(query=["ангел"]))
    assert not _lacks_season(
        franchise("ангел", [row("Ангел / Angel S01 1080p", "d")]), Args(query=["ангел"])
    )


def test_a_movie_pool_never_lacks_a_season() -> None:
    """Сериалов в выдаче нет вовсе - сезонному кругу тут не за чем ходить."""
    found = franchise("кино", [row("Кино / Movie (1999) BDRip 1080p", "e")])

    assert not _lacks_season(found, Args(query=["кино"]))
