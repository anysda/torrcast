"""Обложки прогрессивной выдачи: имя только у легших байтов, дозапрос после тишины, потолок."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

import hass.search_progress as module
from hass.hit_posters import FIELD, HitPosters
from hass.poster_shelf import PosterShelf
from hass.search_progress import search_progress
from tests.test_hit_claims import _Clock, _Storm
from tests.test_hit_posters import FakeSource
from tests.test_search_progress import _CARS, _CONFIG, _detect, _PreviewClient, _remember
from tests.usecases.discover.world import wire_catalogue
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover.search_circle import search_circle

#: Опрос страницы не ждёт байтов картинки: ответ за это время, секунды.
_QUICK = 1.0
_SETTLE = 3.0


class _Circles:
    """Круг поиска на подделке индексеров; считает, сколько раз его звали."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        #: Повторный круг стоит, пока проба его не отпустит: так он не успевает сесть.
        self.hold = threading.Event()
        self.client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)

    def __call__(self, config: Config, args: Any, said: Any, profile: Any, hook: Any) -> Any:
        self.asked.append(args.title_query)
        if len(self.asked) > 1:
            self.hold.wait(_SETTLE)
        hook(self.client)
        return search_circle(
            config,
            args,
            said,
            profile,
            indexer=lambda *_a, **_k: self.client,
            passport=lambda *_a, **_k: Origin(),
        )


def _poll(circles: _Circles, posters: HitPosters) -> tuple[list[Any], bool]:
    return search_progress(
        _CONFIG, "тачки", _detect, _remember, search=circles, offer=posters.urgent, covers=posters
    )


def _final(circles: _Circles, posters: HitPosters, wanted: Any = bool) -> list[Any]:
    deadline = time.monotonic() + _SETTLE
    results, partial = _poll(circles, posters)
    while (partial or not wanted(results)) and time.monotonic() < deadline:
        threading.Event().wait(0.02)
        results, partial = _poll(circles, posters)
    assert partial is False
    return results


def _cars(results: list[Any]) -> dict[str, Any]:
    return next(hit for hit in results if hit["title"] == "Тачки")


@pytest.fixture(autouse=True)
def _fresh_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_jobs", {})
    wire_catalogue()


def test_a_poll_names_a_poster_only_once_its_bytes_are_here(tmp_path: Path) -> None:
    """🔴 TC-1286: имя раньше байтов держало соединение браузера до 6 с на плитку."""
    gate = threading.Event()
    posters = HitPosters(FakeSource(gate=gate), PosterShelf(home=lambda: tmp_path))
    circles = _Circles()
    try:
        results = _final(circles, posters)
        began = time.monotonic()
        results, _ = _poll(circles, posters)
        assert time.monotonic() - began < _QUICK
        assert FIELD not in _cars(results), "имя ушло странице раньше байтов"
        assert posters.pending(results), "страница перестала бы ждать едущую обложку"
    finally:
        gate.set()
    results = _final(circles, posters, lambda said: FIELD in _cars(said))
    assert FIELD in _cars(results) and not posters.pending(results)


def test_a_verdict_held_by_429_is_asked_again_by_a_poll_after_the_quiet(tmp_path: Path) -> None:
    """Пустой ответ в минуту 429 спрашивается снова опросом, заставшим конец тишины."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(calm=130.0)
    posters = HitPosters(source, PosterShelf(home=lambda: tmp_path), clock, storm)
    circles = _Circles()
    results = _final(circles, posters)
    assert FIELD not in _cars(results) and posters.pending(results)
    asked = len(source.judged)
    _poll(circles, posters)
    assert len(source.judged) == asked, "до конца тишины картину спросили снова"
    clock.now, storm.troubled, source.pages = 130.0, False, {"Тачки": ["Cars"]}
    results = _final(circles, posters, lambda said: FIELD in _cars(said))
    assert FIELD in _cars(results)
    assert circles.asked == ["тачки"], "дозапрос обложек погнал круг поиска второй раз"


def test_a_job_with_posters_coming_outlives_its_ttl_but_not_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Заход с обложками в пути не сменяется новым кругом, но только до потолка."""
    gate = threading.Event()
    posters = HitPosters(FakeSource(gate=gate), PosterShelf(home=lambda: tmp_path))
    circles = _Circles()
    try:
        _final(circles, posters)
        monkeypatch.setattr(module, "JOB_TTL", -1.0)
        _, partial = _poll(circles, posters)
        assert partial is False, "обложки в пути, а заход сменился новым кругом"
        monkeypatch.setattr(module, "POSTERS_BY", 0.0)
        _, partial = _poll(circles, posters)
        assert partial is True, "зависший дозапрос держит заход вечно"
        deadline = time.monotonic() + _SETTLE
        while len(circles.asked) < 2 and time.monotonic() < deadline:
            threading.Event().wait(0.02)
        assert circles.asked == ["тачки", "тачки"], "зависший дозапрос держит заход вечно"
    finally:
        circles.hold.set()
        gate.set()


def test_the_poll_that_sees_the_covers_end_after_the_ttl_gets_the_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Обложки кончились позже срока захода: опрос, заставший конец, получает финал."""
    gate = threading.Event()
    posters = HitPosters(FakeSource(gate=gate), PosterShelf(home=lambda: tmp_path))
    circles = _Circles()
    try:
        assert posters.pending(_final(circles, posters))
        monkeypatch.setattr(module, "JOB_TTL", -1.0)
        gate.set()
        deadline = time.monotonic() + _SETTLE
        while posters.pending(module._jobs["тачки"].results) and time.monotonic() < deadline:
            threading.Event().wait(0.02)
        results, partial = _poll(circles, posters)
        assert partial is False, "конец обложек за сроком захода сменил заход новым"
        assert FIELD in _cars(results) and circles.asked == ["тачки"]
    finally:
        circles.hold.set()
        gate.set()
