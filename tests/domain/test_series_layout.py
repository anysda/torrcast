"""Раскладка сериала из каталога: та из IMDb и TVmaze, что сходится с раздачами."""

from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.series_layout import series_layout

NOW = "2026-09-15T08:00:00+00:00"


def _aired(
    seasons: dict[int, int], when: str = "2010-01-01"
) -> dict[tuple[int, int], tuple[str, str]]:
    return {(s, n): (when, when) for s, count in seasons.items() for n in range(1, count + 1)}


def _counts(layout: tuple[dict[int, list[tuple[int, str]]], bool]) -> dict[int, int]:
    return {season: len(rows) for season, rows in layout[0].items()}


def _direct(layout: tuple[dict[int, list[tuple[int, str]]], bool]) -> bool:
    return layout[1]


def test_the_layout_that_holds_the_releases_wins_interns() -> None:
    """IMDb: четыре сезона по 60; TVmaze и раздачи: сезоны по 20."""
    imdb = {1: tuple(range(1, 61)), 2: tuple(range(1, 61))}
    releases = [parse_release_name(f"Интерны / Сезон: {n} / Серии: 1-20 из 20") for n in (3, 4, 5)]

    layout = series_layout(imdb, _aired(dict.fromkeys(range(1, 6), 20)), releases, [], NOW)

    assert (_counts(layout), _direct(layout)) == (dict.fromkeys(range(1, 6), 20), True)


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


def test_without_tvmaze_imdb_numbering_the_releases_contradict_is_listed_not_direct_interns() -> (
    None
):
    """Раздачи зовут сезон 3, у IMDb его нет: список IMDb есть, но строка s1e45 не s1e45 раздач."""
    imdb = {1: tuple(range(1, 61)), 2: tuple(range(1, 61))}
    releases = [parse_release_name(f"Интерны / Сезон: {n} / Серии: 1-20 из 20") for n in (1, 3)]

    silent = series_layout(imdb, {}, releases, [], NOW)
    assert (_counts(silent), _direct(silent)) == ({1: 60, 2: 60}, False)
    single = [parse_release_name(f"Интерны s{n}e05 WEB-DL") for n in (1, 2, 3)]
    assert _direct(series_layout(imdb, {}, single, [], NOW)) is False, "один сезон вне IMDb из трёх"
    live = series_layout(imdb, _aired({1: 20, 2: 20, 3: 20}), releases, [], NOW)
    assert (_counts(live), _direct(live)) == ({1: 20, 2: 20, 3: 20}, True)


INTERNS_IMDB = {1: tuple(range(1, 61)), 2: tuple(range(1, 61)), 3: tuple(range(1, 62))}
INTERNS_TVMAZE = _aired(dict.fromkeys(range(1, 15), 20))


def test_seasons_imdb_knows_named_as_twenty_episodes_each_take_the_tvmaze_numbering() -> None:
    """«Интерны»: пул зовёт только сезоны 1-3 IMDb, но «из 20» у сезона из 60 - промах."""
    releases = [parse_release_name(f"Интерны / Сезон: {n} / Серии: 1-20 из 20") for n in (1, 2, 3)]

    live = series_layout(INTERNS_IMDB, INTERNS_TVMAZE, releases, [], NOW)
    assert (_counts(live), _direct(live)) == (dict.fromkeys(range(1, 15), 20), True)
    silent = series_layout(INTERNS_IMDB, {}, releases, [], NOW)
    assert (_counts(silent), _direct(silent)) == ({1: 60, 2: 60, 3: 61}, False), "без TVmaze"


def test_a_pack_of_seasons_counts_its_total_against_the_seasons_it_names() -> None:
    releases = [parse_release_name("Интерны [S01-03E01-60 of 60] (2010) 6xDVD9")]

    layout = series_layout(INTERNS_IMDB, INTERNS_TVMAZE, releases, [], NOW)

    assert (_counts(layout), _direct(layout)) == (dict.fromkeys(range(1, 15), 20), True)
    assert _direct(series_layout(INTERNS_IMDB, {}, releases, [], NOW)) is False


def test_tvmaze_seasons_past_the_releases_do_not_extend_a_numbering_they_contradict() -> None:
    releases = [parse_release_name("Интерны s1e45 WEB-DL")]

    layout = series_layout(INTERNS_IMDB, INTERNS_TVMAZE, releases, [], NOW)

    assert (_counts(layout), _direct(layout)) == ({1: 60, 2: 60, 3: 61}, True)


def test_releases_numbered_through_fit_only_a_single_season_sled() -> None:
    """«След [Серии 1-224]»: сквозные номера s6e2 не сыграют, а один сезон «Ван-Писа» - да."""
    imdb = {1: tuple(range(1, 31)), 6: (1, 2)}
    releases = [parse_release_name("След (2007-2024) SATRip [Серии 1-24 из ?]")]

    assert _direct(series_layout(imdb, _aired({1: 12, 2: 12, 3: 12}), releases, [], NOW)) is False
    assert _direct(series_layout(imdb, {}, releases, [], NOW)) is False
    single = [parse_release_name("Ван-Пис [TV] [1-24 из 1000+] [RUS(int)]")]
    one = series_layout({1: tuple(range(1, 31))}, {}, single, [], NOW)
    assert (_counts(one), _direct(one)) == ({1: 30}, True)


def test_an_episode_still_to_come_carries_its_date() -> None:
    aired = {**_aired({1: 1}), (1, 2): ("2026-09-21T01:00:00+00:00", "2026-09-20")}
    releases = [parse_release_name("Show S01E01")]

    layout = series_layout({1: (1, 2)}, aired, releases, [], NOW)

    assert layout == ({1: [(1, ""), (2, "2026-09-20")]}, True)


def test_dates_are_not_borrowed_across_a_different_season_numbering() -> None:
    aired = {(1, 1): ("2026-09-21", "2026-09-21")}
    layout = series_layout({1: (1, 2)}, aired, [], [], NOW)

    assert layout == ({1: [(1, ""), (2, "")]}, True)


def test_a_series_no_catalogue_knows_has_no_layout() -> None:
    assert series_layout({}, {}, [parse_release_name("Show S01E01")], [], NOW) == ({}, False)
