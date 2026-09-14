"""Повтор круга по записи: те же планы, и ни одного вопроса живому каталогу."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.not_found_error import NotFoundError
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover.replay_indexer import ReplayIndexer
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.discover.told_circle import ToldCircle
from torrcast.usecases.select.plan import Plan

_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p | D", "b", size_gb=5.0, seeders=44),
]


def _circle(client: IndexerClient) -> list[Plan]:
    wire_catalogue()
    return search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=["тачки"]),
        Said(),
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: Origin(),
    )


def test_the_written_circle_is_built_again_without_the_catalogue() -> None:
    live = _circle(Indexer(answers={"тачки": _CARS}))
    assert isinstance(live, ToldCircle) and live.told

    again = _circle(ReplayIndexer(live.told))

    titles = [(plan.picture.title, [r.raw_name for r in plan.ranked]) for plan in again]
    assert titles == [(plan.picture.title, [r.raw_name for r in plan.ranked]) for plan in live]


def test_a_question_the_record_does_not_hold_finds_nothing() -> None:
    replay = ReplayIndexer([("search", "тачки", 0.0, (), _CARS)])

    with pytest.raises(NotFoundError):
        replay.search("вверх")
    assert (replay.late(), replay.spare(), replay.search("тачки")) == ([], 0.0, _CARS)
