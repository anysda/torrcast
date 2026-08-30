"""Проверяет обратный разбор готовой строки хронометража в минуты."""

import pytest

from torrcast.domain.facts.hms import hms
from torrcast.domain.facts.minutes_of import minutes_of


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русские слова, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английскую надпись, а рассказывал бы про русскую.
    """


def test_a_ready_runtime_line_reads_back_as_a_number() -> None:
    """Число нужно отбору: битрейт релиза считается делением размера на длительность."""
    assert minutes_of("2 ч 49 мин") == 169
    assert minutes_of("1 ч") == 60
    assert minutes_of("47 мин") == 47


def test_an_unreadable_runtime_is_zero_not_a_guess() -> None:
    """Пусто или не разобралось - ноль; выдумывать длительность нечем."""
    assert minutes_of("") == 0
    assert minutes_of("около двух часов") == 0


def test_the_pair_survives_a_round_trip() -> None:
    """Строку пишет :func:`hms`, читает :func:`minutes_of` - и число не меняется."""
    for minutes in (1, 47, 60, 116, 169):
        assert minutes_of(hms(minutes)) == minutes
