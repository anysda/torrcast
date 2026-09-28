"""Обложка готового сериала может перейти только его именованному спецвыпуску."""

from __future__ import annotations

from hass.serial_parent_posters import serial_parent_posters
from torrcast.domain.json_value import JsonValue


def test_a_serial_special_gets_the_ready_poster_of_its_parent() -> None:
    parent: JsonValue = {
        "title": "Призрак в доспехах: У истоков",
        "year": 2013,
        "kind": "tv",
        "original": "Ghost in the Shell Arise",
        "poster": "parent",
    }
    special: JsonValue = {
        "title": "Призрак в доспехах: Истоки",
        "year": 2013,
        "kind": "tv",
        "original": "Ghost in the Shell Arise",
    }

    covered = serial_parent_posters([parent, special], lambda name: name == "parent")

    assert isinstance(covered[1], dict) and covered[1]["poster"] == "parent"


def test_a_neighbour_serial_never_lends_its_poster() -> None:
    """Соседнее имя, другой год, фильм и пустое имя остаются без обложки."""
    walking: JsonValue = {
        "year": 2010,
        "kind": "tv",
        "original": "The Walking Dead",
        "poster": "walking",
    }
    fear: JsonValue = {
        "year": 2015,
        "kind": "tv",
        "original": "Fear the Walking Dead",
        "poster": "fear",
    }
    single: JsonValue = {"year": 2010, "kind": "tv", "poster": "single"}
    special: JsonValue = {"year": 2015, "kind": "tv", "original": "Fear the Walking Dead Flight"}
    fear_missing: JsonValue = {"year": 2015, "kind": "tv", "original": "Fear the Walking Dead"}
    who_1963: JsonValue = {"year": 1963, "kind": "tv", "original": "Doctor Who"}
    who_2013: JsonValue = {
        "year": 2013,
        "kind": "tv",
        "original": "Doctor Who",
        "poster": "special",
    }
    film: JsonValue = {"year": 2015, "kind": "movie", "original": "The Walking Dead Movie"}

    def ready(_name: str) -> bool:
        return True

    for records in (
        [walking, fear, special],
        [single, special],
        [walking, film],
        [walking, fear_missing],
        [who_2013, who_1963],
    ):
        assert "poster" not in serial_parent_posters(records, ready)[-1]  # type: ignore[operator]
