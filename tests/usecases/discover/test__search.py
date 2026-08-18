"""Зеркало круга поиска: запрос - планы меню, а отказ у него всегда со словом."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.cli.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._search import _search
from torrcast.usecases.select import _Plan

_CONFIG = Config(prowlarr_apikey="KEY")
_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p | D", "b", size_gb=5.0, seeders=44),
]


def _found(answers: dict[str, list[RawResult]], query: str) -> list[_Plan]:
    wire_catalogue()
    client = Indexer(answers=answers)
    return _search(
        _CONFIG,
        Args(query=query.split()),
        Said(),
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: Origin(),
    )


def test_the_query_becomes_the_plans_of_the_menu() -> None:
    """Что нашлось, то и встаёт пунктами меню - в порядке франшизы, а не выдачи."""
    plans = _found({"тачки": _CARS}, "тачки")

    assert [plan.picture.title for plan in plans] == ["Тачки", "Тачки 2"]
    assert all(plan.ranked for plan in plans)


def test_the_kin_of_the_menu_travels_with_every_plan() -> None:
    """Соседи по франшизе нужны там, где у выбранной картины годного не окажется вовсе."""
    plans = _found({"тачки": _CARS}, "тачки")

    assert all(plan.kin == plans[0].kin for plan in plans)


def test_an_empty_catalogue_is_a_refusal_with_a_word() -> None:
    """Молчаливых отказов не бывает: пустая выдача называет сам запрос."""
    with pytest.raises(NotFoundError, match="по запросу «нетакого» ничего не нашлось"):
        _found({}, "нетакого")


def test_without_prowlarr_the_search_is_an_infra_failure_not_a_refusal() -> None:
    """Искать нечем - это поломка настройки, а не «ничего не нашлось»."""
    wire_catalogue()
    with pytest.raises(InfraError, match="не настроен Prowlarr"):
        _search(Config(), Args(query=["тачки"]), Said(), indexer=lambda *_a, **_k: Indexer())
