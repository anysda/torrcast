"""Зеркало строки о запросе второго захода: справка его изменила - об этом говорят."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import releases, row
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._query_note import _query_note


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русская строка о том, что запрос изменила справка."""


#: Русская выдача, в которой оригинала нет вовсе: без справки второго запроса не было бы.
_BLIND = releases([row("Крики и шёпоты (1972) BDRip 1080p", "a")])
#: Та же картина, но оригинал лежит прямо в имени раздачи.
_SEEING = releases([row("Психо / Psycho (1960) BDRip 1080p", "b")])


def test_a_name_only_the_facts_know_names_the_translit_it_replaced() -> None:
    """Оригинала в выдаче нет - без справки заход ушёл бы транслитом, и это сказано."""
    line = _query_note("крики и шёпоты", "Viskningar och rop", _BLIND, Origin(title="Viskningar"))

    assert line == "оригинал «Viskningar och rop» - по справке; без неё искал бы «kriki i shepoty»"


def test_without_a_pool_there_would_be_no_second_query_at_all() -> None:
    """Ни выдачи, ни транслита многословного имени - без справки заходить было бы нечем."""
    line = _query_note("крики и шёпоты", "Viskningar och rop", [], Origin(title="Viskningar"))

    assert line == "оригинал «Viskningar och rop» - по справке; без неё второго запроса не было бы"


def test_a_changed_query_names_what_it_would_have_been() -> None:
    """Справка увела запрос в сторону от выдачи - человек вправе знать, куда именно."""
    line = _query_note("психо", "Psychosis", _SEEING, Origin(title="Psychosis"))

    assert line == "оригинал «Psychosis» - по справке; без неё искал бы «Psycho»"


def test_when_the_facts_changed_nothing_there_is_nothing_to_say() -> None:
    """Совпали - справка тут ничего не решила, и строка была бы шумом."""
    assert _query_note("психо", "Psycho", _SEEING, Origin(title="Psycho")) == ""


def test_a_silent_passport_says_nothing_either() -> None:
    """Справка промолчала - запрос выбрала выдача, и говорить о справке нечего."""
    assert _query_note("психо", "Psycho", _SEEING, Origin()) == ""
