"""Проверяет отметку перенесённых плиток: считается только честное число своей полки."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.carried import CARRIED, carried


def test_the_mark_names_each_shelf_on_its_own() -> None:
    """Отметка каждой полки своя: соседняя полка чужого счёта не видит."""
    body: dict[str, JsonValue] = {CARRIED: {"fresh": 12, "popular": 0}}

    assert carried(body, "fresh") == 12
    assert carried(body, "popular") == 0


def test_a_body_without_the_mark_carries_nothing() -> None:
    """Тело прежних выпусков отметки не знает - в нём ничего не перенесено."""
    assert carried({"fresh": []}, "fresh") == 0


def test_a_malformed_mark_carries_nothing() -> None:
    """Порча на диске не превращается в вычитание мусора из длины полки."""
    assert carried({CARRIED: ["fresh"]}, "fresh") == 0
    assert carried({CARRIED: {"fresh": "12"}}, "fresh") == 0
