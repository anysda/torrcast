"""Зеркало :mod:`torrcast.domain.frames.keymap.key_map`: карта вместе с ценой её снятия.

Цена лежит в самой карте не для красоты: у холодной раздачи снятие индекса стоит секунд
старта, и замер этих секунд обязан ехать вместе с ответом, а не считаться сбоку.
"""

from __future__ import annotations

from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.point import Point


def test_the_map_carries_the_price_of_taking_it() -> None:
    """Байты и заходы - часть ответа: по ним и судят, дорого ли обошлась карта."""
    found = KeyMap(120.0, (Point(0.0, 0, 1),), 262144, 2, "mkv")

    assert (found.duration, found.taken, found.requests) == (120.0, 262144, 2)
    assert found.points == (Point(0.0, 0, 1),)


def test_the_container_is_remembered_because_asking_again_costs_requests() -> None:
    """Контейнер уже известен по первым байтам головы, и дальше он едет даром.

    Молчание тут законно: карту собирают и вручную, а решения по контейнеру принимает тот,
    кто её снял.
    """
    assert KeyMap(1.0, (), 0, 1).kind == ""
    assert KeyMap(1.0, (), 0, 1, "mp4").kind == "mp4"
