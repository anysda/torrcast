"""Зеркало :mod:`torrcast.domain.digest._words`: время, вес и безымянные поля записи."""

from __future__ import annotations

import pytest

from torrcast.domain.digest._words import _facts, _gb, _hms


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русские слова выжимки, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английские строки ``cast log``, а рассказывал бы про русские.
    """


def test_time_is_read_as_a_clock_and_the_hour_appears_only_when_it_is_there() -> None:
    """Минуты и секунды всегда, часы - когда есть: «0:00:07» человек читает хуже, чем «0:07»."""
    assert _hms(7) == "0:07"
    assert _hms(605) == "10:05"
    assert _hms(3725) == "1:02:05"


def test_a_negative_position_reads_as_the_very_beginning() -> None:
    """Приёмник иногда отдаёт отрицательную позицию; минус в выжимке - это шум, а не факт."""
    assert _hms(-5) == "0:00"


def test_the_size_is_told_in_gigabytes_because_that_is_what_the_budget_counts() -> None:
    """Бюджет прогрева человек держит в гигабайтах, а не в байтах."""
    assert _gb(2_500_000_000) == "2.5 ГБ"


def test_the_envelope_never_gets_printed_among_the_facts_of_an_event() -> None:
    """Конверт одинаков у всех записей: напечатай его - и каждая строка стала бы вдвое шумнее."""
    told = _facts({"at": 1.0, "sid": "s", "pid": 2, "phase": "timeline", "event": "x", "слот": 7})

    assert told == " (слот=7)"


def test_an_event_without_facts_adds_no_empty_brackets() -> None:
    """Пустые скобки в конце строки - мусор, которого в выжимке быть не должно."""
    assert _facts({"at": 1.0, "sid": "s", "phase": "show", "event": "x"}) == ""
