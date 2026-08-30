"""Зеркало :mod:`torrcast.domain.digest._event_line`: чья это ветка и что, если ничья.

Главное тут - последний рубеж: событие, о котором ЭТА версия не знает, обязано попасть в
выжимку со всеми своими полями. До TC-194 целый класс записей выпадал в «вернуть пусто», и
человек в ``cast log`` их не видел вовсе, хотя в файле они лежали.
"""

from __future__ import annotations

import pytest

from tests.domain.digest.rows import rec
from torrcast.domain.digest._event_line import _event_line


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русские слова выжимки, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английские строки ``cast log``, а рассказывал бы про русские.
    """


def test_the_stamp_counts_from_the_start_of_the_session_and_not_from_the_epoch() -> None:
    """Время в строке - секунды от начала сеанса: стенное человеку тут не нужно."""
    told = _event_line(rec("buffering", at=1700.0, pos=0.0), 1697.5)

    assert told.startswith("+   2.5с ")


def test_a_timeline_phase_gets_printed_with_its_own_numbers() -> None:
    """У фаз критического пути своей ветки нет, и числа у каждой свои - печатаются как есть."""
    told = _event_line(rec("отбор релиза", phase="timeline", релиз=2), 0.0)

    assert "фаза «отбор релиза» (релиз=2)" in told


def test_an_event_this_version_does_not_know_is_still_shown_with_its_facts() -> None:
    """Пустая строка читалась бы как «события не было», а оно было и лежит в файле."""
    told = _event_line(rec("совсем_новое", phase="новая", поле=7), 0.0)

    assert "новая/совсем_новое (поле=7)" in told


def test_a_known_event_never_falls_through_to_the_last_resort() -> None:
    """Ветка нашлась - строка её, а не свалка полей: иначе разбор дублировал бы сам себя."""
    told = _event_line(rec("buffering", pos=125.0), 0.0)

    assert told.endswith("ребуфер на 2:05")
    assert "(" not in told, "поля события напечатаны своей веткой, а не свалкой"


def test_an_event_that_is_told_by_the_session_summary_stays_silent_here() -> None:
    """Конец сеанса печатает итог блока - второй раз о нём говорить незачем."""
    assert _event_line(rec("session_end", phase="session", pos=10.0), 0.0) == ""
