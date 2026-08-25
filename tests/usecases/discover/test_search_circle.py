"""Зеркало круга поиска: запрос - планы меню, а отказ у него всегда со словом."""

from __future__ import annotations

import pytest

from tests.fakes.state_store import FakeStateStore
from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.facts.origin import Origin
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.ports.state_store.slot import install
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.select.plan import Plan

_CONFIG = Config(prowlarr_apikey="KEY")
_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p | D", "b", size_gb=5.0, seeders=44),
]


def _found(answers: dict[str, list[RawResult]], query: str) -> list[Plan]:
    wire_catalogue()
    client = Indexer(answers=answers)
    return search_circle(
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
        search_circle(Config(), Args(query=["тачки"]), Said(), indexer=lambda *_a, **_k: Indexer())


def test_the_count_of_the_late_travels_with_every_plan() -> None:
    """🔴 TC-703. Признак неполноты каталога нужен отказу по пустой очереди, а он поздний."""
    wire_catalogue()
    client = Indexer(answers={"тачки": _CARS}, waiting=("JacRed",))
    plans = search_circle(
        _CONFIG,
        Args(query=["тачки"]),
        Said(),
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: Origin(),
    )

    assert all(plan.waiting() == ("JacRed",) for plan in plans)


_QUINN = [
    row(
        "Харли Квинн / Harley Quinn [S02] (2020) WEB-DL 1080p, Dub (The Kitchen Russia)",
        "c",
        size_gb=5.0,
        seeders=30,
    ),
    row(
        "Харли Квинн / Harley Quinn [S02] (2020) WEB-DL 1080p, MVO (Good People)",
        "d",
        size_gb=5.0,
        seeders=90,
    ),
]


def _watched(studio: str) -> None:
    """Состояние, в котором эту картину уже смотрели названной студией."""
    store = FakeStateStore()
    state = store.load()
    state.entries["tv:харли-квинн:2020"] = Entry(
        title="Харли Квинн",
        magnet="magnet:?xt=urn:btih:" + "e" * 40,
        kind="tv",
        query="харли-квинн-s2e1",
        studio=studio,
    )
    store.save(state)
    install(store)


def test_the_season_border_keeps_the_studio_the_series_was_watched_with() -> None:
    """Сезон кончился вместе с раздачей, а сериал продолжается той же озвучкой."""
    _watched("The Kitchen Russia")
    plans = _found({"харли квинн": _QUINN}, "харли квинн s2e1")

    assert "The Kitchen Russia" in plans[0].ranked[0].raw_name


def test_without_the_memory_the_top_is_the_most_seeded_one() -> None:
    """Памяти нет - ступень плоская, и наверху стоит тот же, кто стоял всегда."""
    _watched("")
    plans = _found({"харли квинн": _QUINN}, "харли квинн s2e1")

    assert "Good People" in plans[0].ranked[0].raw_name
