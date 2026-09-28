"""Серия за краем раздачи: её называет каталог сериала, а не список серий раздачи."""

from __future__ import annotations

from collections.abc import Mapping

from hass.catalog_next import catalog_next
from torrcast.domain.entry import Entry
from web.series_catalog import SeriesCatalog

NOW = "2026-09-15T08:00:00+00:00"
AIRED = "2020-01-01T02:00:00+00:00"
LATER = "2027-01-01T02:00:00+00:00"
Aired = Mapping[tuple[int, int], tuple[str, str]]


def _catalog(imdb: Mapping[int, tuple[int, ...]], aired: Aired | None = None) -> SeriesCatalog:
    def series_id(title: str, _original: str, _year: int | None) -> str:
        return "tt0000001" if title == "Show" else ""

    def tvmaze(_tconst: str, _wait: float) -> tuple[Aired, bool]:
        return aired or {}, False

    return SeriesCatalog(series_id, lambda _t: imdb, tvmaze, lambda: NOW)


def _at(season: int, episode: int, *, title: str = "Show", kind: str = "tv") -> Entry:
    # Раздача одной серии: список серий раздачи о соседях не знает ничего.
    return Entry(
        title=title,
        magnet="magnet:?xt=1",
        kind="tv" if kind == "tv" else "movie",
        season=season,
        episode=episode,
        episodes=[[season, episode, 0, 0]],
    )


def test_a_lone_episode_of_a_running_season_is_followed_by_the_next_episode() -> None:
    assert catalog_next(_at(8, 3), _catalog({8: (1, 2, 3, 4, 5)})) == "s8e4"


def test_the_last_episode_of_a_season_is_followed_by_the_next_season() -> None:
    assert catalog_next(_at(1, 18), _catalog({1: tuple(range(1, 19)), 2: (1, 2)})) == "s2e1"


def test_the_last_episode_of_the_series_has_no_next() -> None:
    assert catalog_next(_at(1, 5), _catalog({1: (1, 2, 3, 4, 5)})) is None


def test_an_episode_not_on_air_yet_is_not_next() -> None:
    aired = {(1, 1): (AIRED, ""), (1, 2): (AIRED, ""), (2, 1): (LATER, "2027-01-01")}
    assert catalog_next(_at(1, 2), _catalog({1: (1, 2), 2: (1,)}, aired)) is None
    aired[(2, 1)] = (AIRED, "")
    assert catalog_next(_at(1, 2), _catalog({1: (1, 2), 2: (1,)}, aired)) == "s2e1"


def test_an_episode_the_catalogue_does_not_number_is_not_guessed_past() -> None:
    # Сквозная нумерация раздачи: s5e3 в каталоге, где один сезон на 60 серий, - не сосед s1e4.
    assert catalog_next(_at(5, 3), _catalog({1: tuple(range(1, 61))})) is None


def test_a_film_and_a_series_outside_the_catalogue_have_no_next() -> None:
    assert catalog_next(_at(1, 1, kind="movie"), _catalog({1: (1, 2)})) is None
    assert catalog_next(_at(1, 1, title="Unknown"), _catalog({1: (1, 2)})) is None
