"""Проверяет сроки добора справки под язык продукта: русский прежний, чужой с доплатой."""

import pytest

from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.domain.facts.facts_budget import facts_budget
from torrcast.domain.facts.settings import FACTS_BUDGET, HTTP_TIMEOUT


def test_the_russian_menu_waits_exactly_what_it_waited_before() -> None:
    """🔴 Русский показ не платит за правку ни сотой: у него как была одна волна, так и есть."""
    _choose_tongue(RU)

    assert facts_budget() == FACTS_BUDGET


def test_a_foreign_tongue_is_given_the_room_of_its_second_wave() -> None:
    """🔴 TC-957. Под чужим языком до первой печати ДВЕ волны, и потолок обязан их считать.

    Не считал - и английское меню опаздывало к потолку всякий раз: описания приезжали
    после 1.5 с, а к этой секунде список был уже напечатан голым, и второго шанса у
    описания нет (:func:`~torrcast.usecases.choice._shown._shown`).
    """
    _choose_tongue(EN)

    assert facts_budget() == pytest.approx(FACTS_BUDGET + HTTP_TIMEOUT)
