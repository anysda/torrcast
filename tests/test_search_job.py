"""Зеркало захода поиска: выдача и карточка платят за запрос один круг."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from hass.search_job import SearchJob
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.warm_cache import WarmCache

_MOVIE = Picture(title="Interstellar", year=2014, kind="movie")
_MOVIE.releases = [Release(raw_name="Interstellar 2014 BDRip 1080p", title="Interstellar")]
_PLAN = Plan(picture=_MOVIE, ranked=list(_MOVIE.releases), runtime=8520.0, warn_mbit=12.0)


def _detect(_config: Config) -> Choice:
    return Choice(CAUTIOUS, "тест")


def _remember(*_args: Any, **_kwargs: Any) -> None:
    return None


def _as_is(results: list[Any]) -> list[Any]:
    return results


def _warm(spawned: list[Callable[[], None]]) -> tuple[WarmCache, list[str]]:
    """Кэш, чей собственный круг только считается: платить за запрос обязан поиск."""
    own: list[str] = []

    def circle(query: str) -> list[Plan]:
        own.append(query)
        return [_PLAN]

    return WarmCache(circle=circle, blurbs=lambda _p: None, spawn=spawned.append), own


@pytest.mark.machine
def test_the_search_circle_is_the_one_the_card_and_the_warm_up_take() -> None:
    """🔴 Выдача гнала свой круг мимо кэша, и первая плитка той же выдачи - второй."""
    spawned: list[Callable[[], None]] = []
    warm, own = _warm(spawned)
    gate = threading.Event()
    searched: list[str] = []

    def search(config: Config, args: Any, said: Any, profile: Any, on_indexer: Any) -> Any:
        searched.append(args.title_query)
        gate.wait(2.0)
        return [_PLAN]

    job = SearchJob()
    runner = threading.Thread(
        target=job.run,
        args=(Config(), "Interstellar", _detect, _remember, search, _as_is, warm),
    )
    runner.start()
    while not searched:
        threading.Event().wait(0.01)
    queued = warm.ask(["Interstellar"]) + warm.hint("Interstellar")
    card: list[list[Plan]] = []
    opener = threading.Thread(target=lambda: card.append(warm.take("Interstellar ")))
    opener.start()
    gate.set()
    runner.join(3.0)
    opener.join(3.0)

    assert job.done and job.error is None
    assert [hit["title"] for hit in job.results if isinstance(hit, dict)] == ["Interstellar"]
    assert card == [[_PLAN]]
    assert warm.take("Interstellar") == [_PLAN]
    pumps = [spawn for spawn in spawned if spawn == warm._pump]
    assert (searched, own, queued, pumps) == (["Interstellar"], [], 0, [])


def test_a_deadline_final_does_not_overwrite_a_landed_circle() -> None:
    """Опрос увидел срок, а круг сел раньше его финала: досчитанное превью не затирает."""
    job = SearchJob()
    job.settle([{"key": "circle"}], landed=True)
    job.settle([{"key": "preview"}])
    assert job.results == [{"key": "circle"}]
    job.settle([{"key": "verdict"}], landed=True)
    assert job.results == [{"key": "verdict"}]


def test_a_poster_once_named_is_not_taken_away_by_a_silent_verdict() -> None:
    """Превью в минуту 429 молчит об уже найденной обложке: имя у плитки остаётся."""
    job = SearchJob()
    hits: list[Any] = [{"key": "cars"}]
    job._judge(hits, lambda records: [{"key": "cars", "poster": "p"} for _ in records])
    job._judge(hits, lambda records: records)
    assert job.dress(hits, _as_is) == [{"key": "cars", "poster": "p"}]
