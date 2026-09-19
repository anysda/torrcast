"""Быстрый ответ карточки до готовности круга раздач."""

import json
import threading
import time
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

    class _UntouchedRelated(_Related):
        def __init__(self) -> None:
            self.asked = False

        def of(self, _title: str, _series: bool) -> None:
            self.asked = True
            return None

    related = _UntouchedRelated()
    answer = preview(request, "movie:luca:2021", _Warm(), related)

    assert answer is not None
    assert json.loads(answer.body)["blurb"] is None
    assert json.loads(answer.body)["related"] is None
    assert not related.asked


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


def test_a_confirmed_missing_article_still_asks_the_page_to_wait_for_the_circle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 «Пропавшая»: без статьи и без родни раздачи всё равно едут, опрос не кончается."""
    monkeypatch.setattr(web.preview, "MenuFacts", _MissingFacts)
    request = Request(
        method="GET",
        path="/api/card/tv:lost:2026",
        query={"query": "Lost", "title": "Пропавшая", "year": "2026", "kind": "tv"},
        body={},
    )

    answer = preview(request, "tv:lost:2026", _Warm(), _Related())

    assert answer is not None
    assert json.loads(answer.body)["searching"] is True
    assert ("X-Torrcast-Partial", "1") in answer.extra


def test_a_blank_query_does_not_crash_a_preview_with_real_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Прямая ссылка шлёт пустое ``query=``: разбор строки роняет его из ``request.query``
    вовсе (``urllib.parse.parse_qs`` без ``keep_blank_values``), и подстрочник с ``[...]``
    на его месте валил страницу ``KeyError`` вместо честного скелета."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None
    assert json.loads(answer.body)["searching"] is True


def test_a_blank_query_does_not_crash_a_long_poll_either(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тот же обрыв, но во втором чтении ``query`` - на долгом опросе (``wait=1``)."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    monkeypatch.setattr(web.preview, "PATIENCE", 0.0)
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"title": "Лука", "year": "2021", "kind": "movie", "wait": "1"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), _Related())

    assert answer is not None
    assert json.loads(answer.body)["searching"] is True


def test_a_waiting_preview_gives_way_as_soon_as_the_circle_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Готовый круг не досиживает терпение справки: полная карточка отвечает сразу."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    monkeypatch.setattr(web.preview, "PATIENCE", 5.0)
    monkeypatch.setattr(web.preview, "_sleep", lambda _seconds: None)
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie", "wait": "1"},
        body={},
    )

    class _LandingWarm(_Warm):
        looks = 0

        def ready(self, _query: str) -> object | None:  # type: ignore[override]
            self.looks += 1
            return None if self.looks == 1 else ["plan"]

    started = time.monotonic()
    answer = preview(request, "movie:luca:2021", _LandingWarm(), _Related())

    assert answer is None
    assert time.monotonic() - started < 1.0


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


def test_a_card_promotes_a_hovered_fact_flight_to_foreground(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A screen's hover must not claim card priority before the person clicks it."""
    monkeypatch.setattr(web.preview, "MenuFacts", _Facts)
    flights = web.preview._FactFlights()

    hover = flights.of("Лука", 2021, "movie", foreground=False)
    card = flights.of("Лука", 2021, "movie")

    assert card is hover
    assert card.foreground


def test_a_click_gets_its_own_flight_in_front_of_an_unfinished_hover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hovered flight already waits behind the background; the click does not wait with it."""

    class _Flying(_Facts):
        def __init__(self, pictures: object, budget: float) -> None:
            super().__init__(pictures, budget)
            self._done = threading.Event()

    monkeypatch.setattr(web.preview, "MenuFacts", _Flying)
    flights = web.preview._FactFlights()

    hover = flights.of("Лука", 2021, "movie", foreground=False)
    card = flights.of("Лука", 2021, "movie")
    poll = flights.of("Лука", 2021, "movie")

    assert card is not hover
    assert card.foreground
    assert not hover.foreground
    assert poll is card


def test_a_click_keeps_an_unfinished_hover_that_already_brought_the_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hover's description has arrived and only its decorations fly: the click takes it."""

    class _Described(_Facts):
        def __init__(self, pictures: object, budget: float) -> None:
            super().__init__(pictures, budget)
            self._done = threading.Event()
            self.found = {("Лука", 2021): _Fact()}

    monkeypatch.setattr(web.preview, "MenuFacts", _Described)
    flights = web.preview._FactFlights()

    hover = flights.of("Лука", 2021, "movie", foreground=False)
    card = flights.of("Лука", 2021, "movie")

    assert card is hover
    assert card.foreground


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


def test_a_related_tile_without_an_article_still_gets_its_shelf_by_the_known_qid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Нет статьи - текст «описания нет», но полку даёт Q-код, с которым плитку показали."""
    from torrcast.domain.facts.kin import Kin
    from torrcast.domain.json_value import JsonValue
    from web.kin_ahead import KinAhead

    ahead = KinAhead()
    ahead.offer([Kin("Q471", "Лука", 2021)])
    monkeypatch.setattr(web.preview, "KIN_AHEAD", ahead)
    monkeypatch.setattr(web.preview, "MenuFacts", _MissingFacts)

    class _KnownRelated:
        def __init__(self) -> None:
            self.entities: list[str] = []

        def waiting(self, _title: str, _series: bool) -> bool:
            return False

        def of(self, _title: str, _series: bool, *entity: str) -> list[JsonValue] | None:
            self.entities.extend(entity or ("",))
            return [{"key": "movie:coco:2017", "title": "Тайна Коко"}]

    related = _KnownRelated()
    request = Request(
        method="GET",
        path="/api/card/movie:luca:2021",
        query={"query": "Luca", "title": "Лука", "year": "2021", "kind": "movie"},
        body={},
    )

    answer = preview(request, "movie:luca:2021", _Warm(), related)

    assert answer is not None
    assert json.loads(answer.body)["blurb"] == ""
    assert json.loads(answer.body)["related"][0]["title"] == "Тайна Коко"
    assert related.entities and set(related.entities) == {"Q471"}
