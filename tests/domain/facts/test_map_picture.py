"""Зеркало :mod:`torrcast.domain.facts.map_picture`: строка карты с голосами."""

import dataclasses

import pytest

from torrcast.domain.facts.map_picture import MapPicture


def test_a_map_picture_is_a_frozen_value() -> None:
    """Картину карты делят разные запросы одного процесса: править её на месте нельзя."""
    picture = MapPicture(name="Мы", year=2019, series=False, original="Us", votes=399488)

    with pytest.raises(dataclasses.FrozenInstanceError):
        picture.votes = 0  # type: ignore[misc]
    assert picture == MapPicture("Мы", 2019, False, "Us", 399488)
