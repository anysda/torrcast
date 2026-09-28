"""Раздачи идущего круга: счёт карточки растёт с первым индексером, показ не ждёт хвоста."""

from __future__ import annotations

import json
from typing import Any

import pytest

import web.early_picture as early
import web.preview
import web.show_stage as show_stage
from tests.test_preview import _Facts, _Related, _Warm
from tests.usecases.discover.world import row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.raw_result import RawResult
from web.early_picture import early_picture
from web.request import Request

KEY = "movie:матрица:1999"
_MATRIX = [
    row("Матрица / The Matrix (1999) BDRip 1080p", "a"),
    row("Матрица / The Matrix (1999) WEB-DL 720p", "b", indexer="RuTor"),
]


@pytest.fixture(autouse=True)
def _catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    wire_catalogue()
    monkeypatch.setattr(early, "_seen", {})


class _Rows:
    """Выдача идущего круга, которую тест доливает по индексеру."""

    def __init__(self) -> None:
        self.raw: list[RawResult] = []

    def __call__(self, _query: str) -> tuple[list[RawResult], list[RawResult], None]:
        return list(self.raw), [], None


def test_the_picture_is_found_in_what_the_first_indexer_sent() -> None:
    rows = _Rows()
    assert early_picture("матрица", KEY, rows) is None  # никто ещё не ответил
    rows.raw = _MATRIX[:1]
    first = early_picture("матрица", KEY, rows)
    assert first is not None and len(first.releases) == 1
    rows.raw = list(_MATRIX)
    grown = early_picture("матрица", KEY, rows)
    assert grown is not None and len(grown.releases) == 2
    assert early_picture("матрица", "movie:дюна:2021", rows) is None, "чужой ключ"


def test_the_count_never_goes_back_while_the_card_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Щель между концом круга и его записью пуста: счёт карточки не падает в ноль."""
    now = [0.0]
    monkeypatch.setattr(early, "_clock", lambda: now[0])
    rows = _Rows()
    rows.raw = list(_MATRIX)
    assert len(early_picture("матрица", KEY, rows).releases) == 2  # type: ignore[union-attr]
    rows.raw = []  # круг закончился, в кэш ещё не лёг
    held = early_picture("матрица", KEY, rows)
    assert held is not None and len(held.releases) == 2
    rows.raw = _MATRIX[:1]  # новый заход круга начал выдачу сначала
    held = early_picture("матрица", KEY, rows)
    assert held is not None and len(held.releases) == 2
    now[0] = early.HOLD + 1
    rows.raw = []
    assert early_picture("матрица", KEY, rows) is None, "старая находка не держится вечно"


def _card(wait: bool) -> Request:
    query = {"query": "матрица", "title": "Матрица", "year": "1999", "kind": "movie"}
    if wait:
        query["wait"] = "1"
    return Request(method="GET", path="/api/card/" + KEY, query=query, body={})


def test_the_preview_counts_releases_that_already_came(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    monkeypatch.setattr(web.preview, "_facts", web.preview._FactFlights())
    rows = _Rows()
    rows.raw = list(_MATRIX)
    monkeypatch.setattr(web.preview, "early_picture", lambda q, k: early_picture(q, k, rows))
    answer = preview_body(_card(wait=False))
    assert (answer["releases_count"], answer["sources_count"], answer["searching"]) == (2, 2, True)


def test_a_waiting_preview_answers_as_soon_as_the_count_grows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Долгий заход не держит новый счёт до конца своей секунды."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    monkeypatch.setattr(web.preview, "_facts", web.preview._FactFlights())
    rows = _Rows()
    ticks: list[float] = []

    def tick(seconds: float) -> None:
        ticks.append(seconds)
        rows.raw = _MATRIX[:1]  # первый индексер ответил, пока заход ждал

    monkeypatch.setattr(web.preview, "_sleep", tick)
    monkeypatch.setattr(web.preview, "early_picture", lambda q, k: early_picture(q, k, rows))
    answer = preview_body(_card(wait=True))
    assert answer["releases_count"] == 1
    assert len(ticks) == 1


def preview_body(request: Request) -> dict[str, Any]:
    answer = web.preview.preview(request, KEY, _Warm(), _Related())
    assert answer is not None
    said: dict[str, Any] = json.loads(answer.body)
    return said


class _Running:
    def ready(self, _query: str) -> None:
        return None

    def take(self, _query: str) -> list[Any]:
        raise AssertionError("показ ждал конца круга, хотя картина уже пришла")


def test_the_show_plays_from_the_releases_that_already_came(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _Rows()
    rows.raw = list(_MATRIX)
    monkeypatch.setattr(show_stage, "WARM", _Running())
    monkeypatch.setattr(show_stage, "early_picture", lambda q, k: early_picture(q, k, rows))
    args = Args(query=["матрица"], picture=KEY)
    got = show_stage._card_circle(Config(), args, Any, CAUTIOUS)  # type: ignore[arg-type]
    assert [plan.picture.key for plan in got] == [KEY]
    assert len(got[0].picture.releases) == 2
