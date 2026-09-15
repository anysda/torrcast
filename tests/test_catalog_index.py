"""Зеркало указателя каталога: картины по началу имени, русского и оригинального."""

from __future__ import annotations

from hass.catalog_index import MIN_VOTES, CatalogIndex
from torrcast.domain.facts.imdb_rows import _RuName
from torrcast.domain.slugify import slugify

_ROWS: list[_RuName] = [
    ("tt0133093", "movie", "The Matrix", "1999", "Матрица"),
    ("tt0234215", "movie", "The Matrix Reloaded", "2003", "Матрица: Перезагрузка"),
    ("tt9999991", "movie", "Matrix Nobody", "2020", "Матрица безвестная"),
    ("tt9999992", "tvEpisode", "The Matrix", "2001", "Матрица"),
    ("tt1439629", "tvSeries", "Gravity Falls", "2012", "Гравити Фолз"),
    ("tt1454468", "movie", "Gravity", "2013", "Гравитация"),
    ("tt1591054", "tvSeries", "Gravity", "2010", "Гравитация"),
]
_VOTES = {
    "tt0133093": 2_275_526,
    "tt0234215": 676_310,
    "tt9999991": MIN_VOTES - 1,
    "tt9999992": 5_000,
    "tt1439629": 184_404,
    "tt1454468": 905_980,
    "tt1591054": 1_150,
}


def _index() -> CatalogIndex:
    names: dict[str, list[_RuName]] = {}
    for row in _ROWS:
        names.setdefault(slugify(row[4]), []).append(row)
    index = CatalogIndex(lambda: names, lambda: _VOTES)
    index.warm()
    return index


def test_a_russian_prefix_finds_the_known_pictures_exact_name_first() -> None:
    found = [row[0] for row in _index().look("матрица")]
    # Эпизод - не плитка, безвестный тёзка ниже порога голосов.
    assert found == ["tt0133093", "tt0234215"]


def test_an_original_name_finds_the_same_russian_picture() -> None:
    assert [row[4] for row in _index().look("The Matrix")] == ["Матрица", "Матрица: Перезагрузка"]


def test_a_far_less_known_namesake_does_not_take_a_tile() -> None:
    assert [row[4] for row in _index().look("гравит")] == ["Гравитация", "Гравити Фолз"]


def test_an_index_is_silent_before_it_is_warmed_and_on_a_short_query() -> None:
    cold = CatalogIndex(lambda: {"матрица": [_ROWS[0]]}, lambda: _VOTES)
    assert cold.look("матрица") == []
    assert _index().look("ма") == []
    assert _index().by_id("tt1454468") == _ROWS[5]


def _named(*rows: _RuName, votes: dict[str, int]) -> CatalogIndex:
    names: dict[str, list[_RuName]] = {}
    for one in rows:
        names.setdefault(slugify(one[4]), []).append(one)
    index = CatalogIndex(lambda: names, lambda: votes)
    index.warm()
    return index


_US: _RuName = ("tt6857112", "movie", "Us", "2019", "Мы")
_INTERSTELLAR: _RuName = ("tt0816692", "movie", "Interstellar", "2014", "Интерстеллар")
_MOCKBUSTER: _RuName = ("tt4168808", "movie", "Interstelar", "2014", "Интерстелар")
_STAR_VOTES = {"tt6857112": 399_858, "tt0816692": 2_605_028}


def test_a_short_exact_name_is_a_picture_but_not_a_prefix_of_others() -> None:
    index = _named(
        _US, ("tt1", "movie", "Mouse", "2020", "Мышеловка"), votes={**_STAR_VOTES, "tt1": 9_000}
    )
    assert [one[4] for one in index.look("мы")] == ["Мы"]


def test_a_trailing_year_is_not_part_of_the_name() -> None:
    assert [one[4] for one in _named(_US, votes=_STAR_VOTES).look("Мы 2019")] == ["Мы"]


def test_one_letter_off_finds_the_picture_past_an_unknown_namesake_of_the_typo() -> None:
    index = _named(_INTERSTELLAR, _MOCKBUSTER, votes=_STAR_VOTES)
    assert [one[4] for one in index.look("Интерстелар")] == ["Интерстеллар"]
    assert [one[4] for one in index.look("Интерстеллер")] == ["Интерстеллар"]
    assert [one[4] for one in index.look("Interstelar")] == ["Интерстеллар"]


def test_a_typo_is_not_guessed_in_short_words_or_beside_digits() -> None:
    index = _named(
        _INTERSTELLAR,
        ("tt2", "movie", "It 2", "2019", "Оно 2"),
        votes={**_STAR_VOTES, "tt2": 9_000},
    )
    assert index.look("Оно 3") == []
    assert index.look("ывапрол") == []
