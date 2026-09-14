"""Зеркало :mod:`torrcast.usecases.discover._map_kept`: карта поменяла ответ по имени или нет."""

import pytest

from tests.fakes import composition
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.discover._map_kept import _map_kept


def _picture(title: str, year: int, copies: int) -> Picture:
    releases = [Release(raw_name=f"{title} {n}", title=title) for n in range(copies)]
    return Picture(title=title, year=year, releases=releases)


_POOL = [
    _picture("Вверх", 2009, 3),
    _picture("Руки вверх", 1981, 2),
    _picture("Руки вверх", 2024, 9),
]


def test_a_name_the_map_took_back_from_a_word_neighbour_is_crowded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [MapPicture("Вверх", 2009, False, "Up", 1254598)]
    composition.use_known_pictures(monkeypatch, lambda title: rows if title == "Вверх" else [])

    assert _map_kept("Вверх", _POOL)


def test_a_silent_map_changes_nothing_and_the_name_is_not_crowded() -> None:
    assert not _map_kept("Вверх", _POOL)
    assert not _map_kept("Вверх", [])
