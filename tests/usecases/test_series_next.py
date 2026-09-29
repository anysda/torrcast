"""Серия за краем раздачи: её называет каталог сериала, а не список серий раздачи."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from torrcast.adapters.wiki.tvmaze_episodes import TvmazeEpisodes
from torrcast.domain.entry import Entry
from torrcast.ports.series_source import AiredState
from torrcast.runtime.series_facts import SeriesFacts
from torrcast.usecases.series_next import series_next

NOW = "2026-09-15T08:00:00+00:00"
AIRED = "2020-01-01T02:00:00+00:00"
LATER = "2027-01-01T02:00:00+00:00"
Dates = Mapping[tuple[int, int], tuple[str, str]]


def _catalog(
    imdb: Mapping[int, tuple[int, ...]],
    aired: Dates | None = None,
    state: AiredState = AiredState.KNOWN,
) -> SeriesFacts:
    def series_id(title: str, _original: str, _year: int | None) -> str:
        return "tt0000001" if title == "Show" else ""

    def tvmaze(_tconst: str, _wait: float) -> tuple[Dates, bool]:
        return aired or {}, state

    return SeriesFacts(series_id, lambda _t: imdb, tvmaze, lambda: NOW)


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


def test_a_lone_episode_of_a_running_season_is_found_by_the_unit() -> None:
    catalog = _catalog({8: (1, 2, 3, 4, 5)}, state=AiredState.UNKNOWN)
    assert series_next(_at(8, 3), catalog) == (8, 4)
    assert series_next(_at(8, 3), catalog, lambda: ()) is None


def test_a_real_tvmaze_refusal_does_not_offer_a_lone_midseason_episode(tmp_path: Path) -> None:
    def refused(_url: str) -> object:
        raise TimeoutError("refused")

    catalogue = SeriesFacts(
        lambda *_a: "tt0000001",
        lambda _t: {9: (1, 2, 3, 4, 5, 6)},
        TvmazeEpisodes(lambda: tmp_path, refused, lambda job: job(), lambda: 1000.0).aired,
        lambda: NOW,
    )

    assert series_next(_at(9, 5), catalogue, lambda: ()) is None
    assert series_next(_at(9, 5), catalogue) == (9, 6)


def test_a_dated_next_season_is_followed_without_asking_the_pool() -> None:
    aired = {(1, 18): (AIRED, ""), (2, 1): (AIRED, "")}

    def pool() -> tuple[int, ...]:
        raise AssertionError("дата TVmaze уже доказала выход")

    catalog = _catalog({1: tuple(range(1, 19)), 2: (1, 2)}, aired)
    assert series_next(_at(1, 18), catalog, pool) == (2, 1)


def test_an_undated_next_season_needs_releases_in_the_pool() -> None:
    # «Рик и Морти» s9e10: IMDb уже числит анонсированный s10, а TVmaze не ответил.
    catalog = _catalog({9: tuple(range(1, 11)), 10: (1, 2)})
    assert series_next(_at(9, 10), catalog, lambda: (8, 9)) is None
    assert series_next(_at(9, 10), catalog, lambda: None) is None, "пул ещё греется"
    assert series_next(_at(9, 10), catalog, lambda: (9, 10)) == (10, 1)


def test_a_warming_pool_does_not_turn_an_imdb_number_into_an_offer() -> None:
    catalog = _catalog({9: tuple(range(1, 11)), 10: (1,)}, state=AiredState.UNKNOWN)
    assert series_next(_at(9, 10), catalog, lambda: None) is None
    assert series_next(_at(9, 10), catalog) == (10, 1)


def test_the_unit_proves_the_next_season_by_its_own_search() -> None:
    catalog = _catalog({1: tuple(range(1, 19)), 2: (1, 2)})
    assert series_next(_at(1, 18), catalog) == (2, 1)


def test_the_last_episode_of_the_series_has_no_next() -> None:
    assert series_next(_at(1, 5), _catalog({1: (1, 2, 3, 4, 5)})) is None


def test_an_episode_not_on_air_yet_is_not_next() -> None:
    aired = {(1, 1): (AIRED, ""), (1, 2): (AIRED, ""), (2, 1): (LATER, "2027-01-01")}
    assert series_next(_at(1, 2), _catalog({1: (1, 2), 2: (1,)}, aired), lambda: (2,)) is None
    aired[(2, 1)] = (AIRED, "")
    assert series_next(_at(1, 2), _catalog({1: (1, 2), 2: (1,)}, aired)) == (2, 1)


def test_an_episode_the_catalogue_does_not_number_is_not_guessed_past() -> None:
    # Сквозная нумерация раздачи: s5e3 в каталоге, где один сезон на 60 серий, - не сосед s1e4.
    assert series_next(_at(5, 3), _catalog({1: tuple(range(1, 61))})) is None


def test_a_film_and_a_series_outside_the_catalogue_have_no_next() -> None:
    assert series_next(_at(1, 1, kind="movie"), _catalog({1: (1, 2)})) is None
    assert series_next(_at(1, 1, title="Unknown"), _catalog({1: (1, 2)})) is None
