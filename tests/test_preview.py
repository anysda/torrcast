"""Быстрый ответ карточки до готовности круга раздач."""

import json
import threading
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
    missing: bool = False


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


class _AnsweredFacts(_Facts):
    def answered(self, _title: str, _year: int) -> bool:
        return True


class _MissingFacts(_AnsweredFacts):
    def ready(self, _title: str, _year: int) -> _Fact:
        return _Fact(missing=True)


class _EarlyAboutFacts(_Facts):
    def ready(self, _title: str, _year: int) -> _Fact:
        return _Fact(about="A ready description")


class _PendingRelated(_Related):
    def waiting(self, _title: str, _series: bool) -> bool:
        return True


@pytest.fixture(autouse=True)
def _fresh_fact_flights(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подмена источника в одной пробе не должна стать общим добором следующей."""
    monkeypatch.setattr(web.preview, "_facts", web.preview._FactFlights())


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
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None
    assert json.loads(answer.body)["blurb"] is None


def test_an_answered_description_does_not_wait_for_the_related_shelf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Родня дорисуется добором, но не держит уже готовое описание."""
    monkeypatch.setattr(web.preview, "MenuFacts", _AnsweredFacts)
    monkeypatch.setattr(web.preview, "_sleep", lambda _seconds: pytest.fail("waited"))
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _PendingRelated())

    assert answer is not None


def test_an_answered_empty_description_is_not_left_as_a_skeleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A trusted cache absence is useful before the release circle completes."""
    monkeypatch.setattr(web.preview, "MenuFacts", _MissingFacts)
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None
    assert json.loads(answer.body)["blurb"] == ""
    assert json.loads(answer.body)["related"] == []


def test_a_ready_description_is_published_before_later_fact_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wikipedia text is useful before the later Wikidata detail pass is complete."""
    monkeypatch.setattr(web.preview, "MenuFacts", _EarlyAboutFacts)
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None
    assert json.loads(answer.body)["blurb"] == "A ready description"


def test_the_first_preview_never_spends_its_source_patience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Клик обязан поставить скелет до того, как успеет ответить любой источник."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    monkeypatch.setattr(web.preview, "_sleep", lambda _seconds: pytest.fail("waited"))
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None


def test_a_waiting_preview_does_not_fall_through_to_the_release_circle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Второй GET ждёт только факты и родню, пока круг раздач ещё занят."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    monkeypatch.setattr(web.preview, "PATIENCE", 0.0)
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie", "wait": "1"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None


def test_waiting_previews_share_one_unfinished_fact_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Каждый partial-опрос раньше открывал свою волну Wikipedia."""
    made = 0

    class _CountedFacts(_Facts):
        def __init__(self, pictures: object, budget: float) -> None:
            nonlocal made
            made += 1
            super().__init__(pictures, budget)

    monkeypatch.setattr(web.preview, "MenuFacts", _CountedFacts)
    monkeypatch.setattr(web.preview, "PATIENCE", 0.0)
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie", "wait": "1"},
        body={},
    )

    preview(request, "movie:luca:2021", _Warm(), _Related())
    preview(request, "movie:luca:2021", _Warm(), _Related())

    assert made == 1


def test_a_finished_silent_fact_lookup_is_retried_without_its_old_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed source must not keep the card blank until the flight lease expires."""
    made = 0

    class _SilentFacts(_Facts):
        def __init__(self, pictures: object, budget: float) -> None:
            nonlocal made
            made += 1
            super().__init__(pictures, budget)
            self._done = threading.Event()

        def start(self) -> None:
            self._done.set()

    monkeypatch.setattr(web.preview, "MenuFacts", _SilentFacts)
    now = iter([0.0, 3.0])
    monkeypatch.setattr(web.preview.time, "monotonic", lambda: next(now))
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    preview(request, "movie:luca:2021", _Warm(), _Related())
    preview(request, "movie:luca:2021", _Warm(), _Related())

    assert made == 2
