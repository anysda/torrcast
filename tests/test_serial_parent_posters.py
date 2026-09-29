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
