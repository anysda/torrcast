"""Зеркало узнавания картины по карте: имя целиком, год в конце, одна опечатка."""

from __future__ import annotations

from hass.catalog_index import CatalogIndex
from hass.catalog_picture import catalog_picture
from torrcast.domain.facts.imdb_rows import _RuName
from torrcast.domain.slugify import slugify

_ROWS: list[_RuName] = [
    ("tt0816692", "movie", "Interstellar", "2014", "Интерстеллар"),
    ("tt4168808", "movie", "Interstelar", "2014", "Интерстелар"),
    ("tt0133093", "movie", "The Matrix", "1999", "Матрица"),
    ("tt0234215", "movie", "The Matrix Reloaded", "2003", "Матрица: Перезагрузка"),
    ("tt1396484", "movie", "It", "2017", "Оно"),
    ("tt0099864", "tvMiniSeries", "It", "1990", "Оно"),
    ("tt0409591", "tvSeries", "Naruto", "2002", "Наруто"),
    ("tt0000011", "movie", "Molot", "2001", "Молот"),
    ("tt0000012", "movie", "Motor", "2001", "Мотор"),
]
_VOTES = {
    "tt0816692": 2_605_028,
    "tt0133093": 2_277_240,
    "tt0234215": 676_310,
    "tt1396484": 709_523,
    "tt0099864": 150_000,
    "tt0409591": 174_119,
    "tt0000011": 5_000,
    "tt0000012": 4_000,
}


def _index() -> CatalogIndex:
    names: dict[str, list[_RuName]] = {}
    for row in _ROWS:
        names.setdefault(slugify(row[4]), []).append(row)
    index = CatalogIndex(lambda: names, lambda: _VOTES)
    index.warm()
    return index


def _name(query: str) -> tuple[str, int | None, bool] | None:
    picture = catalog_picture(_index(), query)
    return None if picture is None else (picture.original, picture.year, picture.series)


def test_a_whole_name_is_the_best_known_picture_of_that_name() -> None:
    assert _name("Оно") == ("It", 2017, False)
    assert _name("The Matrix") == ("The Matrix", 1999, False)
    assert _name("Наруто") == ("Naruto", 2002, True)


def test_a_trailing_year_picks_the_namesake_of_that_year() -> None:
    assert _name("Оно 1990") == ("It", 1990, True)
    assert _name("Матрица 2003") is None


def test_one_typo_names_the_picture_but_a_prefix_does_not() -> None:
    assert _name("Интерстелар") == ("Interstellar", 2014, False)
    assert _name("Interstelar 2014") == ("Interstellar", 2014, False)
    assert _name("Матр") is None
    assert _name("ывапрол") is None


def test_a_typo_between_two_near_pictures_of_like_fame_names_nothing() -> None:
    assert _name("Мотот") is None


def test_a_cold_map_names_nothing() -> None:
    cold = CatalogIndex(lambda: {}, lambda: {})
    assert catalog_picture(cold, "Оно") is None
