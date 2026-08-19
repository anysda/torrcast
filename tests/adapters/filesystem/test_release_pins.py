"""Порядок показанной таблицы раздач: номер значит то же, что и минуту назад."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.filesystem.release_pins import ReleasePins
from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.domain.release import Release

FIRST = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"
SECOND = "0123456789abcdef0123456789abcdef01234567"


def _release(info_hash: str) -> Release:
    return Release(raw_name="Тачки.2006", title="Тачки", magnet=f"magnet:?xt=urn:btih:{info_hash}")


def test_a_number_from_the_table_names_the_same_release() -> None:
    """Номер строки возвращает хэш той раздачи, что стояла в этой строке."""
    pins = ReleasePins()
    pins.remember("тачки", {"Тачки": [_release(FIRST), _release(SECOND)]})

    assert pins.recalled("тачки", "Тачки", 1) == FIRST
    assert pins.recalled("тачки", "Тачки", 2) == SECOND


def test_numbers_outside_the_table_give_nothing() -> None:
    """Номера вне таблицы, чужой запрос и чужая картина - пусто, а не соседняя раздача."""
    pins = ReleasePins()
    pins.remember("тачки", {"Тачки": [_release(FIRST)]})

    assert pins.recalled("тачки", "Тачки", 0) == ""
    assert pins.recalled("тачки", "Тачки", 2) == ""
    assert pins.recalled("моана", "Тачки", 1) == "", "номер помнится в границах своего запроса"
    assert pins.recalled("тачки", "Моана", 1) == ""


def test_the_next_table_of_the_same_query_replaces_the_previous_one() -> None:
    """Номер живёт до следующей таблицы: иначе вчерашняя двойка играла бы сегодня."""
    pins = ReleasePins()
    pins.remember("тачки", {"Тачки": [_release(FIRST), _release(SECOND)]})
    pins.remember("тачки", {"Тачки": [_release(SECOND)]})

    assert pins.recalled("тачки", "Тачки", 1) == SECOND
    assert pins.recalled("тачки", "Тачки", 2) == ""


def test_a_missing_or_broken_file_is_not_a_crash() -> None:
    """Файла нет или в нём лежит чужое - пусто, а не отказ показа."""
    pins = ReleasePins()
    assert pins.recalled("тачки", "Тачки", 1) == ""

    path = state_path().with_name("release-pins.json")
    path.write_text("{не json", encoding="utf-8")
    assert pins.recalled("тачки", "Тачки", 1) == ""

    path.write_text('{"тачки": {"Тачки": [1, 2]}}', encoding="utf-8")
    assert pins.recalled("тачки", "Тачки", 1) == "", "в таблице обязаны лежать имена, а не числа"

    path.write_text('{"тачки": "не таблица"}', encoding="utf-8")
    assert pins.recalled("тачки", "Тачки", 1) == ""


def test_the_table_lands_beside_the_state_file() -> None:
    """Файл с порядком едет за состоянием, а не остаётся в чужом каталоге."""
    pins = ReleasePins()
    pins.remember("тачки", {"Тачки": [_release(FIRST)]})

    beside = Path(state_path()).with_name("release-pins.json")
    assert beside.exists()
