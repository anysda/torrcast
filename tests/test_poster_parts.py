"""Зеркало :mod:`hass.poster_parts`: пачка делится по адресам, а часть не ждёт соседнюю."""

from __future__ import annotations

import threading

from hass.poster_parts import poster_parts
from torrcast.domain.facts.ask import Ask

CARS = Ask(title="Тачки", year=2006, kind="movie")
IT, IT_TWO = Ask(title="Оно", year=2017, kind="movie"), Ask(title="Оно 2", year=2019, kind="movie")


def test_pictures_with_the_same_addresses_go_as_one_part() -> None:
    """Общий постер сборника и первой части качается одним походом, а не двумя."""
    seen: list[dict[Ask, list[str]]] = []
    lock = threading.Lock()

    def land(part: dict[Ask, list[str]]) -> None:
        with lock:
            seen.append(part)

    poster_parts({CARS: ["cars.jpg"], IT: ["it.jpg"], IT_TWO: ["it.jpg"]}, land)
    assert sorted(seen, key=len) == [{CARS: ["cars.jpg"]}, {IT: ["it.jpg"], IT_TWO: ["it.jpg"]}]


def test_a_part_lands_while_another_is_still_on_its_way() -> None:
    """Застрявшая часть не держит соседнюю: та ложится, пока первая ещё в пути."""
    gate, landed = threading.Event(), threading.Event()

    def land(part: dict[Ask, list[str]]) -> None:
        if IT in part:
            assert gate.wait(5.0) and landed.is_set(), "часть ждала соседнюю"
        else:
            landed.set()
            gate.set()

    poster_parts({IT: ["it.jpg"], CARS: ["cars.jpg"]}, land)
    assert landed.is_set()
