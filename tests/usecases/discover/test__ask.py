"""Зеркало круга по индексерам: пустая выдача - не ошибка."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, row
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._ask import _ask


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - поведение круга поиска."""


class _Empty(Indexer):
    """Каталог, который на всё отвечает отказом: строк нет вовсе."""

    def search(self, query: str) -> list[RawResult]:
        self.asked.append(query)
        raise NotFoundError(f"по запросу «{query}» ничего не нашлось")


def test_the_rows_of_the_circle_come_back_as_they_are() -> None:
    """Что каталог ответил, то круг и отдаёт - разбирать их будет уже не он."""
    client = Indexer([row("Психо / Psycho (1960) BDRip 1080p")])

    assert len(_ask(client, "психо")) == 1
    assert client.asked == ["психо"]


def test_an_empty_answer_is_not_a_failure() -> None:
    """Пусто - это повод переспросить иначе, а не ошибка: наверх едет пустой список."""
    assert _ask(_Empty(), "сфкы") == []
