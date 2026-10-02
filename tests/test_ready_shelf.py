"""Проверяет состав полки на миг «готово»: после него полка только усыхает."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.ready_shelf import ReadyShelf


def _tiles(*keys: str, poster: str = "p") -> list[JsonValue]:
    return [{"key": key, "poster": poster} for key in keys]


def _shown(ready: ReadyShelf, fresh: list[JsonValue], popular: list[JsonValue]) -> None:
    ready.saw("fresh", fresh)
    ready.saw("popular", popular)


def test_before_ready_every_tile_passes() -> None:
    """Счётчик горит: полка растёт как угодно."""
    ready = ReadyShelf()

    assert ready.watch(True) is True
    assert ready.keep("fresh", _tiles("a", "b"), {}) == _tiles("a", "b")


def test_after_ready_a_new_tile_is_held_back_and_only_a_verdict_drops_one() -> None:
    """Погас счётчик - новая картина не встаёт; снимает только приговор «не играет»."""
    ready = ReadyShelf()
    ready.watch(True)
    _shown(ready, _tiles("a", "b"), _tiles("x"))

    assert ready.watch(False) is False
    assert ready.keep("fresh", _tiles("c"), {}) == _tiles("a", "b")
    assert ready.keep("fresh", _tiles("a", "c"), {"b": False, "a": None}) == _tiles("a")


def test_a_ready_tile_keeps_the_cover_the_page_saw() -> None:
    """Другая обложка той же картины в новом заходе не подменяет показанную."""
    ready = ReadyShelf()
    ready.watch(True)
    _shown(ready, _tiles("a"), _tiles("x"))
    ready.watch(False)

    assert ready.keep("fresh", _tiles("a", poster="other"), {}) == _tiles("a")


def test_once_out_the_counter_never_burns_again() -> None:
    """Добор ленты после «готово» не зажигает счётчик снова."""
    ready = ReadyShelf()
    ready.watch(True)
    _shown(ready, _tiles("a"), _tiles("x"))
    ready.watch(False)

    assert ready.watch(True) is False


def test_an_empty_shelf_is_not_frozen() -> None:
    """Пустая полка не «готова»: состав не застывает, следующий заход её наполнит."""
    ready = ReadyShelf()
    ready.watch(True)
    _shown(ready, _tiles("a"), [])

    assert ready.watch(False) is False
    assert ready.watch(True) is True
    assert ready.keep("popular", _tiles("x"), {}) == _tiles("x")


def test_a_warm_rebuild_whose_counter_never_burned_keeps_growing() -> None:
    """Тёплая пересборка счётчика не зажигала: «готово» не было, добор полку растит."""
    ready = ReadyShelf()
    _shown(ready, _tiles("a"), _tiles("x"))

    assert ready.watch(False) is False
    assert ready.keep("fresh", _tiles("a", "b"), {}) == _tiles("a", "b")


def test_a_shelf_condemned_to_empty_drops_the_freeze() -> None:
    """Приговоры сняли всё: «готово» держать нечем, счётчик снова горит над пустой полкой."""
    ready = ReadyShelf()
    ready.watch(True)
    _shown(ready, _tiles("a"), _tiles("x"))
    ready.watch(False)

    assert ready.keep("fresh", _tiles("a"), {"a": False}) == []
    assert ready.tiles is None
    assert ready.watch(True) is True
