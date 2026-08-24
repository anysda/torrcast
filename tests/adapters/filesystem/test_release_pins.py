"""Порядок показанной таблицы раздач: номер значит то же, что и минуту назад."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.filesystem.release_pins import ReleasePins
from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.domain.release import Release

FIRST = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"
SECOND = "0123456789abcdef0123456789abcdef01234567"

KEY = "movie:тачки:2006"
NAME = "Тачки (2006)"


def _release(info_hash: str) -> Release:
    return Release(raw_name="Тачки.2006", title="Тачки", magnet=f"magnet:?xt=urn:btih:{info_hash}")


def _shown(*rows: tuple[str, str, list[Release]]) -> list[tuple[str, str, list[Release]]]:
    """Строки таблицы в показанном порядке: ключ картины, её имя и раздачи."""
    return list(rows)


def _cars(*hashes: str) -> tuple[str, str, list[Release]]:
    """Строка таблицы первых «Тачек» с раздачами под переданными хэшами."""
    return KEY, NAME, [_release(each) for each in hashes]


def test_a_number_from_the_table_names_the_same_release() -> None:
    """Номер строки возвращает хэш той раздачи, что стояла в этой строке."""
    pins = ReleasePins()
    pins.remember("тачки", _shown(_cars(FIRST, SECOND)))

    assert pins.recalled("тачки", KEY, 1) == FIRST
    assert pins.recalled("тачки", KEY, 2) == SECOND


def test_numbers_outside_the_table_give_nothing() -> None:
    """Номера вне таблицы, чужой запрос и чужая картина - пусто, а не соседняя раздача."""
    pins = ReleasePins()
    pins.remember("тачки", _shown(_cars(FIRST)))

    assert pins.recalled("тачки", KEY, 0) == ""
    assert pins.recalled("тачки", KEY, 2) == ""
    assert pins.recalled("моана", KEY, 1) == "", "номер помнится в границах своего запроса"
    assert pins.recalled("тачки", "movie:тачки-2:2011", 1) == ""


def test_the_next_table_of_the_same_query_replaces_the_previous_one() -> None:
    """Номер живёт до следующей таблицы: иначе вчерашняя двойка играла бы сегодня."""
    pins = ReleasePins()
    pins.remember("тачки", _shown(_cars(FIRST, SECOND)))
    pins.remember("тачки", _shown(_cars(SECOND)))

    assert pins.recalled("тачки", KEY, 1) == SECOND
    assert pins.recalled("тачки", KEY, 2) == ""


def test_a_missing_or_broken_file_is_not_a_crash() -> None:
    """Файла нет или в нём лежит чужое - пусто, а не отказ показа."""
    pins = ReleasePins()
    assert pins.recalled("тачки", KEY, 1) == ""
    assert pins.recalled_picture("тачки", 1) == ("", "")

    path = state_path().with_name("release-pins.json")
    path.write_text("{не json", encoding="utf-8")
    assert pins.recalled("тачки", KEY, 1) == ""
    assert pins.recalled_picture("тачки", 1) == ("", "")

    path.write_text('{"тачки": {"shown": {"movie:тачки:2006": [1, 2]}}}', encoding="utf-8")
    assert pins.recalled("тачки", KEY, 1) == "", "в таблице обязаны лежать имена, а не числа"

    path.write_text('{"тачки": "не таблица"}', encoding="utf-8")
    assert pins.recalled("тачки", KEY, 1) == ""


def test_a_table_of_the_previous_format_still_names_its_releases() -> None:
    """Файл до появления порядка картин - плоский: раздачи из него читаются, как читались."""
    path = state_path().with_name("release-pins.json")
    path.write_text(f'{{"тачки": {{"{KEY}": ["{FIRST}"]}}}}', encoding="utf-8")

    pins = ReleasePins()
    assert pins.recalled("тачки", KEY, 1) == FIRST
    assert pins.recalled_picture("тачки", 1) == ("", ""), "порядка картин в старом файле нет"


def test_a_pick_number_names_the_picture_that_stood_under_it() -> None:
    """Номер картины - тот же адрес, что номер раздачи: ключ и имя стоявшей под ним."""
    pins = ReleasePins()
    pins.remember(
        "тачки",
        _shown(_cars(FIRST), ("movie:тачки-2:2011", "Тачки 2 (2011)", [_release(SECOND)])),
    )

    assert pins.recalled_picture("тачки", 1) == (KEY, NAME)
    assert pins.recalled_picture("тачки", 2) == ("movie:тачки-2:2011", "Тачки 2 (2011)")
    assert pins.recalled_picture("тачки", 3) == ("", ""), "номера за границей таблицы нет"
    assert pins.recalled_picture("моана", 1) == ("", ""), "чужой запрос - не эта таблица"


def test_the_table_lands_beside_the_state_file() -> None:
    """Файл с порядком едет за состоянием, а не остаётся в чужом каталоге."""
    pins = ReleasePins()
    pins.remember("тачки", _shown(_cars(FIRST)))

    beside = Path(state_path()).with_name("release-pins.json")
    assert beside.exists()


def test_the_menu_remembers_its_picture_order_without_a_release_table() -> None:
    """Меню нумерует картины, но не раздачи: номеров раздач в его записи нет."""
    pins = ReleasePins()
    pins.remember_menu("тачки", [(KEY, NAME), ("movie:тачки-2:2011", "Тачки 2 (2011)")])

    assert pins.recalled_picture("тачки", 1) == (KEY, NAME)
    assert pins.recalled_picture("тачки", 2) == ("movie:тачки-2:2011", "Тачки 2 (2011)")
    assert pins.recalled("тачки", KEY, 1) == "", "номеров раздач меню не показывало"


def test_the_menu_keeps_the_release_table_of_the_same_query() -> None:
    """Таблица раздач - от последнего ``cast releases``: меню её не переписывает.

    Порядок раздач под пунктами меню человек не видел никогда: запомни его меню -
    и номер из таблицы молча адресовал бы другую раздачу.
    """
    pins = ReleasePins()
    pins.remember("тачки", _shown(_cars(FIRST, SECOND)))
    pins.remember_menu("тачки", [("movie:тачки-2:2011", "Тачки 2 (2011)"), (KEY, NAME)])

    assert pins.recalled("тачки", KEY, 2) == SECOND, "номера раздач видели в таблице"
    assert pins.recalled_picture("тачки", 1) == ("movie:тачки-2:2011", "Тачки 2 (2011)")


def test_a_menu_of_another_query_forgets_the_whole_table() -> None:
    """Номер живёт до следующего показанного списка - даже списка чужого запроса."""
    pins = ReleasePins()
    pins.remember("тачки", _shown(_cars(FIRST)))
    pins.remember_menu("моана", [("movie:моана:2016", "Моана (2016)")])

    assert pins.recalled("тачки", KEY, 1) == ""
    assert pins.recalled_picture("тачки", 1) == ("", "")


def test_the_menu_keeps_a_release_table_of_the_previous_format() -> None:
    """Плоский файл до появления порядка картин меню тоже бережёт: раздачи читаются."""
    path = state_path().with_name("release-pins.json")
    path.write_text(f'{{"тачки": {{"{KEY}": ["{FIRST}"]}}}}', encoding="utf-8")

    pins = ReleasePins()
    pins.remember_menu("тачки", [(KEY, NAME)])

    assert pins.recalled("тачки", KEY, 1) == FIRST
    assert pins.recalled_picture("тачки", 1) == (KEY, NAME)


def test_the_next_table_replaces_what_the_menu_remembered() -> None:
    """Свежая таблица того же запроса переписывает и порядок картин, и раздачи."""
    pins = ReleasePins()
    pins.remember_menu("тачки", [(KEY, NAME)])
    pins.remember("тачки", _shown(_cars(FIRST)))

    assert pins.recalled("тачки", KEY, 1) == FIRST
    assert pins.recalled_picture("тачки", 1) == (KEY, NAME)
