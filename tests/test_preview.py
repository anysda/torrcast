"""Быстрый ответ карточки до готовности круга раздач."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

import web.preview
from web.preview import _year, preview
from web.request import Request


@dataclass
class _Fact:
    rating: str = ""
    about: str = ""


class _Facts:
    def __init__(self, _pictures: object, budget: float) -> None:
        self.budget = budget

    def start(self) -> None:
        pass

    def ready(self, _title: str, _year: int) -> _Fact:
        return _Fact()

    def answered(self, _title: str, _year: int) -> bool:
        return False


class _Warm:
    def ready(self, _query: str) -> None:
        return None

    def ask(self, _queries: Sequence[str]) -> int:
        return 1


class _Related:
    def of(self, _title: str, _series: bool) -> None:
        return None

    def waiting(self, _title: str, _series: bool) -> bool:
        return False


def test_a_preview_year_rejects_a_route_without_a_real_year() -> None:
    """Без точного года ключ не даёт права назвать факты картины."""
    assert _year("2014") == 2014
    assert _year("2014.5") is None
    assert _year("1700") is None


def test_an_unanswered_fact_stays_a_skeleton_not_a_false_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пустое описание назовёт лишь ответивший источник, а не быстрый preview."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    monkeypatch.setattr(web.preview, "PATIENCE", 0.0)
    request = Request(
        method="GET", path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"}, body={}
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None
    assert json.loads(answer.body)["blurb"] is None
