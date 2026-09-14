"""Запуск полки открытой карточки."""

from types import SimpleNamespace

import pytest

import web.start_related
from torrcast.domain.facts.kin import Kin
from web.kin_ahead import KinAhead
from web.request import Request
from web.start_related import start_related


class _Facts:
    def of(self, *_args: object) -> "_Facts":
        return self

    def ready(self, *_args: object) -> SimpleNamespace:
        return SimpleNamespace(entity="Q104905")


class _Related:
    asked: tuple[str, bool, str] | None = None

    def retry(self, title: str, series: bool, entity: str) -> None:
        self.asked = title, series, entity


def test_an_opened_tile_reuses_its_fact_qid() -> None:
    request = Request(
        method="GET",
        path="/api/card/movie:wall-e:2008",
        query={"title": "ВАЛЛ-И", "year": "2008", "kind": "movie"},
        body={},
    )
    related = _Related()

    hint = start_related(request, _Facts(), related)

    assert hint == ("ВАЛЛ-И", 2008, "movie")
    assert related.asked == ("ВАЛЛ-И", False, "Q104905")


def test_a_related_tile_starts_its_shelf_by_the_qid_of_the_shelf_that_showed_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Плитка родни не ждёт статью: её Q-код приехал с полкой, что её показала."""
    ahead = KinAhead()
    ahead.offer([Kin("Q471", "Тайна Коко", 2017)])
    monkeypatch.setattr(web.start_related, "KIN_AHEAD", ahead)
    request = Request(
        method="GET",
        path="/api/card/movie:coco:2017",
        query={"title": "Тайна Коко", "year": "2017", "kind": "movie"},
        body={},
    )
    related = _Related()

    start_related(request, _SilentFacts(), related)

    assert related.asked == ("Тайна Коко", False, "Q471")


class _SilentFacts(_Facts):
    def ready(self, *_args: object) -> SimpleNamespace:
        return SimpleNamespace(entity="")
