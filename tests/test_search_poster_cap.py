"""Опрос обложек у потолка сервера не заводит второй поиск того же запроса."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any, cast

import pytest

import hass.search_progress as module
from hass.search_job import POSTERS_BY, SearchJob
from hass.search_progress import CAP_GRACE, search_progress


class _Waiting:
    """Память картинок, у которой обложки ещё в пути."""

    def pending(self, _results: Any) -> bool:
        return True

    def due(self, _results: Any) -> bool:
        return False

    def has(self, _name: Any) -> bool:
        return False


@pytest.fixture
def circles(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    started: list[int] = []

    def run(_job: SearchJob, *_args: Any) -> None:
        started.append(1)

    monkeypatch.setattr(SearchJob, "run", run)
    module._jobs.clear()
    yield started
    module._jobs.clear()


def _poll_at(age: float) -> SearchJob:
    """Опрашивает запрос, чей готовый заход начат ``age`` секунд назад."""
    now = time.monotonic()
    job = SearchJob(catalog=None)
    job.started_at, job.finished_at, job.done, job.results = now - age, now - age + 15, True, []
    module._jobs["тачки"] = job
    search_progress(
        cast(Any, None), "тачки", cast(Any, None), cast(Any, None), covers=cast(Any, _Waiting())
    )
    return job


def test_a_poll_landing_just_past_the_poster_cap_keeps_its_search(circles: list[int]) -> None:
    """Опрос, ушедший со страницы до потолка, приезжает после него и встаёт в тот же заход."""
    job = _poll_at(POSTERS_BY + 0.2)
    assert not circles, "опрос у потолка завёл новый круг по индексерам"
    assert module._jobs["тачки"] is job


def test_a_poll_long_past_the_poster_cap_starts_afresh(circles: list[int]) -> None:
    _poll_at(POSTERS_BY + CAP_GRACE + 1)
    assert circles == [1], "заход с обложками в пути не должен жить вечно"
