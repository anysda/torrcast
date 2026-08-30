"""Проверяет перевод минут в человеческую строку хронометража."""

import pytest

from torrcast.domain.facts.hms import hms


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русские слова, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английскую надпись, а рассказывал бы про русскую.
    """


def test_running_time_reads_as_a_human_would_say_it() -> None:
    assert hms(116) == "1 ч 56 мин"
    assert hms(47) == "47 мин"
    assert hms(60) == "1 ч", "«1 ч 0 мин» так не говорят"
    assert hms(0) == ""


def test_a_picture_longer_than_a_day_gets_no_line_at_all() -> None:
    """Лучше строка без хронометража, чем строка с выдуманным числом."""
    assert hms(24 * 60) == "24 ч"
    assert hms(24 * 60 + 1) == ""
    assert hms(10809) == ""
