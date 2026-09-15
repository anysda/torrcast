"""Раскладка сериала из каталога: та из IMDb и TVmaze, что сходится с раздачами."""

from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.series_layout import series_layout

NOW = "2026-09-15T08:00:00+00:00"


def _aired(
    seasons: dict[int, int], when: str = "2010-01-01"
) -> dict[tuple[int, int], tuple[str, str]]:
    return {(s, n): (when, when) for s, count in seasons.items() for n in range(1, count + 1)}


def _counts(layout: dict[int, list[tuple[int, str]]]) -> dict[int, int]:
    return {season: len(rows) for season, rows in layout.items()}


def test_the_layout_that_holds_the_releases_wins_interns() -> None:
    """IMDb: четыре сезона по 60; TVmaze и раздачи: сезоны по 20."""
    imdb = {1: tuple(range(1, 61)), 2: tuple(range(1, 61))}
    releases = [parse_release_name(f"Интерны / Сезон: {n} / Серии: 1-20 из 20") for n in (3, 4, 5)]

    layout = series_layout(imdb, _aired(dict.fromkeys(range(1, 6), 20)), releases, [], NOW)

    assert _counts(layout) == dict.fromkeys(range(1, 6), 20)


def test_imdb_wins_a_tie_and_grows_a_season_tvmaze_confirms_futurama() -> None:
    imdb = {6: tuple(range(1, 17)), 7: tuple(range(1, 14)), 8: tuple(range(1, 14))}
    releases = [
        parse_release_name("Футурама / Сезон: 6 / Серии: 1-26 из 26"),
        parse_release_name("Футурама [08x01-05 из 13]"),
    ]
    tvmaze = _aired({6: 26, 7: 26})

    layout = series_layout(imdb, tvmaze, releases, [], NOW)

    assert _counts(layout) == {6: 26, 7: 13, 8: 13}, "s7 без раздачи на 26 не растёт"


def test_imdb_placeholders_past_the_releases_are_not_tabs_while_tvmaze_answers() -> None:
    """«Рик и Морти»: IMDb заводит s10-12 по одной серии, TVmaze их не знает."""
    imdb = {1: (1, 2), 2: (1, 2), 3: (1,)}
    releases = [parse_release_name("Rick and Morty S02E01-02")]

    assert _counts(series_layout(imdb, _aired({1: 2, 2: 2}), releases, [], NOW)) == {1: 2, 2: 2}
    assert _counts(series_layout(imdb, {}, releases, [], NOW)) == {1: 2, 2: 2, 3: 1}, "без сети"
    assert _counts(series_layout(imdb, _aired({1: 2, 2: 2}), releases, [3], NOW))[3] == 1


def test_an_episode_still_to_come_carries_its_date() -> None:
    aired = {**_aired({1: 1}), (1, 2): ("2026-09-21T01:00:00+00:00", "2026-09-20")}
    releases = [parse_release_name("Show S01E01")]

    layout = series_layout({1: (1, 2)}, aired, releases, [], NOW)

    assert layout == {1: [(1, ""), (2, "2026-09-20")]}


def test_dates_are_not_borrowed_across_a_different_season_numbering() -> None:
    aired = {(1, 1): ("2026-09-21", "2026-09-21")}
    layout = series_layout({1: (1, 2)}, aired, [], [], NOW)

    assert layout == {1: [(1, ""), (2, "")]}


def test_a_series_no_catalogue_knows_has_no_layout() -> None:
    assert series_layout({}, {}, [parse_release_name("Show S01E01")], [], NOW) == {}
