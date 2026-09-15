"""Зеркало :mod:`hass.offer_within`: шаг поиска HA не ждёт приговора обложек дольше срока."""

from __future__ import annotations

import threading
import time

import pytest

from hass.hit_ask import _about, _name
from hass.hit_posters import FIELD, hits
from hass.offer_within import offer_within
from hass.searching import searching
from tests.test_searching import _CONFIG, _cautious, _search
from torrcast.domain.json_value import JsonValue

#: Приговор, застрявший в тишине источника: дольше любого разумного шага HA, секунды.
_STUCK = 5.0


def _remember(_query: str, _named: list[tuple[str, str]]) -> None:
    return None


def test_the_ha_step_returns_while_the_poster_verdict_is_stuck() -> None:
    """🔴 TC-1284: шаг HA стоял в приговоре обложек, пока тот ждал тишину Wikimedia."""
    gate = threading.Event()

    def stuck(results: list[JsonValue]) -> list[JsonValue]:
        gate.wait(_STUCK)
        return results

    began = time.monotonic()
    try:
        results = searching(_CONFIG, "тачки", _search, _cautious, _remember, offer=stuck)
    finally:
        gate.set()
    assert time.monotonic() - began < _STUCK / 2, "шаг HA ждал застрявший приговор обложек"
    assert results, "список ушёл пустым вместо списка без обложек"


def _named(said: list[JsonValue]) -> list[JsonValue]:
    return [{**one, FIELD: "x"} if isinstance(one, dict) else one for one in said]


def test_a_verdict_in_time_is_handed_over_whole() -> None:
    """Успевший приговор отдаётся как есть: срок не отнимает имён у спокойного источника."""
    assert offer_within(_named, [{"title": "Оно"}]) == [{"title": "Оно", FIELD: "x"}]


def test_a_late_verdict_leaves_only_landed_pictures_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """К сроку имя остаётся у картинки, чьи байты здесь: маршрут отдаст её без ожидания."""
    gate = threading.Event()
    cars_ask = _about({"title": "Тачки", "year": 2006})
    assert cars_ask is not None
    monkeypatch.setattr(hits, "has", lambda name: name == _name(cars_ask))

    def late(said: list[JsonValue]) -> list[JsonValue]:
        gate.wait(_STUCK)
        return _named(said)

    try:
        cars, it = offer_within(late, [{"title": "Тачки", "year": 2006}, {"title": "Оно"}], 0.05)
    finally:
        gate.set()
    assert isinstance(cars, dict) and cars.get(FIELD) and isinstance(it, dict) and FIELD not in it
