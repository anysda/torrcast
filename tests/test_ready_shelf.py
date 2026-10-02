"""Проверяет состав полки на миг «готово»: после него полка только усыхает."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.ready_shelf import ReadyShelf


def _tiles(*keys: str) -> list[JsonValue]:
    return [{"key": key} for key in keys]


def test_before_ready_every_tile_passes() -> None:
    """Счётчик горит: полка растёт как угодно."""
    ready = ReadyShelf()

    assert ready.watch(True, {"fresh": ["a"]}, {}) is True
    assert ready.keep("fresh", _tiles("a", "b")) == _tiles("a", "b")


def test_after_ready_a_new_tile_is_held_back_and_a_dropped_one_stays_gone() -> None:
    """Погас счётчик - новая картина на полку не встаёт, снятая не возвращается в счёт."""
    ready = ReadyShelf()

    assert ready.watch(False, {"fresh": ["a", "b"]}, {}) is False
    assert ready.keep("fresh", _tiles("a", "c")) == _tiles("a")


def test_a_closed_shelf_is_remembered_by_its_published_tiles() -> None:
    """Закрытая полка в ``done``: запоминается её тело, а не устаревший показ."""
    ready = ReadyShelf()

    ready.watch(False, {"popular": ["old"]}, {"popular": _tiles("x", "y")})

    assert ready.keep("popular", _tiles("x", "old", "z")) == _tiles("x")


def test_the_first_ready_moment_is_kept_and_not_moved_later() -> None:
    """Повторный «погас» не переписывает состав: точка отсчёта - первый миг «готово»."""
    ready = ReadyShelf()
    ready.watch(False, {"fresh": ["a"]}, {})

    ready.watch(False, {"fresh": ["a", "b"]}, {})

    assert ready.keep("fresh", _tiles("a", "b")) == _tiles("a")
