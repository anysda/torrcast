"""Зеркало круга по индексерам: пустая выдача - не ошибка, а выпавший источник назван."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, row
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._ask import _ask


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки о выпавших и опоздавших индексерах."""


class _Empty(Indexer):
    """Каталог, который на всё отвечает отказом: строк нет вовсе."""

    def search(self, query: str) -> list[RawResult]:
        self.asked.append(query)
        raise NotFoundError(f"по запросу «{query}» ничего не нашлось")


def test_the_rows_of_the_circle_come_back_as_they_are() -> None:
    """Что каталог ответил, то круг и отдаёт - разбирать их будет уже не он."""
    client = Indexer([row("Психо / Psycho (1960) BDRip 1080p")])

    assert len(_ask(client, "психо", Said())) == 1
    assert client.asked == ["психо"]


def test_an_empty_answer_is_not_a_failure() -> None:
    """Пусто - это повод переспросить иначе, а не ошибка: наверх едет пустой список."""
    assert _ask(_Empty(), "сфкы", Said()) == []


def test_a_fallen_indexer_is_named_out_loud_once_per_search() -> None:
    """🔴 TC-510. Молча источник не выпадает, но и повторяться строка не имеет права."""
    client = Indexer([row("Кино / Movie (2001) BDRip 1080p")], silent=("Knaben",))
    said = Said()

    _ask(client, "кино", said)
    _ask(client, "кино ещё раз", said)

    assert said.notes == ["индексер Knaben не ответил - выдача может быть хуже"]


def test_the_silent_and_the_banned_are_told_apart() -> None:
    """Молчун не ответил нам, а забаненного мы и не спрашивали - строка называет обоих."""
    rows = [row("Кино / Movie (2001) BDRip 1080p")]
    client = Indexer(rows, silent=("Knaben",), banned=("RuTor",))
    said = Said()

    _ask(client, "кино", said)

    assert said.notes == [
        "индексеры выпали из каталога: Knaben не ответил, RuTor недоступен - выдача может быть хуже"
    ]


def test_a_healthy_circle_says_nothing_at_all() -> None:
    """Никто не выпал и никто не опоздал - лишней строке взяться неоткуда."""
    said = Said()

    _ask(Indexer([row("Кино / Movie (2001) BDRip 1080p")]), "кино", said)

    assert said.notes == []


def test_a_late_indexer_is_named_with_words_of_its_own() -> None:
    """🔴 TC-703. Опоздавший не выпал: его выдача может доехать, и слова у него свои."""
    client = Indexer([row("Кино / Movie (2001) BDRip 1080p")], waiting=("JacRed",))
    said = Said()

    _ask(client, "кино", said)
    _ask(client, "кино ещё раз", said)

    assert said.notes == ["индексер JacRed ещё в пути - выдача пока без него, он может доехать"]


def test_several_late_indexers_are_named_by_one_line() -> None:
    """Строка о неполноте каталога одна, сколько бы источников ни было в пути."""
    client = Indexer([row("Кино / Movie (2001) BDRip 1080p")], waiting=("JacRed", "Knaben"))
    said = Said()

    _ask(client, "кино", said)

    assert said.notes == [
        "индексеры ещё в пути: JacRed, Knaben - выдача пока без них, они могут доехать"
    ]


def test_a_source_named_once_is_not_named_twice_by_other_words() -> None:
    """Опорного круг ждёт весь бюджет, а поток его живёт дальше: имя в обоих счётах одно.

    Человек читает строку про ту секунду, в которую она напечатана, и в эту секунду
    источник молчит. Второй строкой о нём же отказ не разбавляется.
    """
    client = Indexer(
        [row("Кино / Movie (2001) BDRip 1080p")], silent=("JacRed",), waiting=("JacRed",)
    )
    said = Said()

    _ask(client, "кино", said)

    assert said.notes == ["индексер JacRed не ответил - выдача может быть хуже"]
