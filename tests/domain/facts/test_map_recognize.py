"""Зеркало :mod:`torrcast.domain.facts.map_recognize`: картина карты по точному имени запроса."""

from __future__ import annotations

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.map_recognize import map_recognize

DUNE = [
    MapPicture("Дюна", 1984, False, "Dune", 190000),
    MapPicture("Дюна", 2021, False, "Dune: Part One", 1000000),
    MapPicture("Дюна", 2000, True, "Dune", 25000),
]


def known(title: str) -> list[MapPicture]:
    return [row for row in DUNE if row.name.casefold() == title.casefold()]


def test_a_bare_name_is_the_best_known_picture_under_it() -> None:
    """«Дюна» без года - фильм 2021 года: его и спросят у индексеров по оригиналу."""
    assert map_recognize(known, "Дюна") == DUNE[1]


def test_a_named_year_picks_its_namesake() -> None:
    assert map_recognize(known, "Дюна 1984") == DUNE[0]
    assert map_recognize(known, "Дюна 1985") == DUNE[0], "год ± 1, как у доказательства"


def test_a_name_the_map_does_not_know_is_not_recognized() -> None:
    assert map_recognize(known, "Дюна 1990") is None
    assert map_recognize(known, "Дюнка") is None


def test_a_year_after_a_series_start_is_not_that_series() -> None:
    """🔴 Сериал 2000 года не узнаётся по 2026-му: такого года у карты нет."""
    assert map_recognize(known, "Дюна 2026") is None
    assert map_recognize(known, "Дюна 2000") == DUNE[2]
