"""Имя картинки выдаётся ровно тем записям, чьи байты уже лежат на полке."""

from __future__ import annotations

from collections.abc import Sequence

from hass.hit_ask import _about, _name
from hass.shown_covers import shown_covers
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue

_CARS: dict[str, JsonValue] = {"title": "Тачки", "year": 2006, "kind": "movie"}
_CARS_2: dict[str, JsonValue] = {"title": "Тачки 2", "year": 2011, "kind": "movie"}
_CARS_NAME = _name(Ask("Тачки", 2006, "movie", ""))
_CARS_2_NAME = _name(Ask("Тачки 2", 2011, "movie", ""))


class _Shelf:
    """Полка, на которой лежат байты названных картин, и никаких других."""

    def __init__(self, *landed: str) -> None:
        self._landed = set(landed)

    def landed(self, record: JsonValue) -> bool:
        ask = _about(record)
        return ask is not None and _name(ask) in self._landed

    def pending(self, _records: Sequence[JsonValue]) -> bool:
        return False

    def due(self, _records: Sequence[JsonValue]) -> bool:
        return False


class _Whole(_Shelf):
    """Полка, отвечающая «байты здесь» о чём угодно, даже о безымянном."""

    def landed(self, _record: JsonValue) -> bool:
        return True


def _posters(shown: list[JsonValue]) -> list[JsonValue]:
    """Имена картинок показанных записей; не запись - ``None``."""
    return [one.get("poster") if isinstance(one, dict) else None for one in shown]


def test_a_record_whose_bytes_are_here_gets_the_name_it_did_not_ask_for() -> None:
    """🔴 Имя ВЫДАЁТСЯ, а не только отнимается: иначе готовая обложка ждёт всю пачку.

    Приговор пачки отвечает целиком, и легшие обложки стояли за сетевым ответом о тех,
    кого нет нигде (TC-1268). Запись пришла без имени, а байты под её именем уже здесь.
    """
    shown = shown_covers([dict(_CARS)], _Shelf(_CARS_NAME))
    assert shown == [{**_CARS, "poster": _CARS_NAME}]


def test_a_record_whose_bytes_are_not_here_loses_the_name_it_came_with() -> None:
    """Имя без байтов держало соединение браузера на маршруте картинки (TC-1286)."""
    shown = shown_covers([{**_CARS, "poster": "чужое-имя"}], _Shelf())
    assert shown == [dict(_CARS)]


def test_the_name_given_is_the_pictures_own_and_not_a_neighbours() -> None:
    """🔴 Чужой картинке взяться неоткуда: имя считается из названия, года и рода.

    Это и есть приёмка «ни одной чужой картинки»: имя не берётся ни из соседней записи,
    ни из ответа источника, а только из опознания самой этой картины.
    """
    shown = shown_covers([dict(_CARS), dict(_CARS_2)], _Shelf(_CARS_NAME, _CARS_2_NAME))
    assert _posters(shown) == [_CARS_NAME, _CARS_2_NAME]


def test_only_the_picture_whose_bytes_landed_is_named_while_its_batch_waits() -> None:
    """Пачка судится целиком, а на экран уходит та, чьи байты уже легли."""
    shown = shown_covers([dict(_CARS), dict(_CARS_2)], _Shelf(_CARS_2_NAME))
    assert _posters(shown) == [None, _CARS_2_NAME]


def test_a_picture_without_a_title_is_left_exactly_as_it_came() -> None:
    """Без названия картинку не ищут: выдумывать ей имя не из чего."""
    nameless: list[JsonValue] = [{"year": 2006, "kind": "movie"}, "не запись"]
    assert shown_covers(nameless, _Whole()) == nameless
