"""Клиент, который помнит сказанное каталогом: по порядку и вместе с отказами."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, row
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.discover.told_indexer import ToldIndexer

_CARS = [row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66)]


class _Refusing(Indexer):
    def search(self, query: str) -> list:  # type: ignore[type-arg]
        raise NotFoundError(query)


def test_every_answer_is_written_down_in_order_and_the_budget_goes_to_the_real_client() -> None:
    inner = Indexer(answers={"тачки": _CARS}, spare=4.5)
    told = ToldIndexer(inner)

    told.search("тачки")
    told.spare()
    told.late()
    told.cap_floor = 2.0

    assert told.told == [
        ("search", "тачки", 0.0, (), _CARS),
        ("spare", "", 4.5, (), []),
        ("late", "", 0.0, (), []),
    ]
    assert inner.cap_floor == 2.0


def test_a_refusal_is_written_down_as_an_empty_answer() -> None:
    told = ToldIndexer(_Refusing())

    with pytest.raises(NotFoundError):
        told.search("пусто")

    assert told.told == [("search", "пусто", 0.0, (), [])]
