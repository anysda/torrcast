"""VoiceLookup: отбор раздачи в фоне, кэш на процесс, прогретое убрано за собой."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.fakes.torrent_engines import FakeTorrentEngines
from tests.usecases.rank.releases import media, track
from torrcast.domain.infra_error import InfraError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.episode_lookup import RETRY
from web.voice_lookup import VoiceLookup

_RELEASE = Release(raw_name="Film 2010 BDRip 1080p LostFilm", title="Film", magnet="magnet:f")
_PICTURE = Picture(title="Film", year=2010, kind="movie", releases=[_RELEASE])
_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE], runtime=0, warn_mbit=0)
_MEDIA = media(tracks=(track(0, "rus", "Dub"), track(1, "eng", "Original")))


@dataclass
class _Prep:
    found: Any
    release: Release = _RELEASE


@dataclass
class _Bench:
    """Подмена стенда отбора: отвечает паспортом или отказом и помнит уборку."""

    answer: Any
    dropped: list[bool] = field(default_factory=list)
    asked: list[tuple[Plan, Any]] = field(default_factory=list)

    def __call__(self, _engine: object, choose: object = None) -> _Bench:
        return self

    def resolve(self, plan: Plan, args: Any, _progress: object) -> _Prep:
        self.asked.append((plan, args))
        if isinstance(self.answer, Exception):
            raise self.answer
        return _Prep(self.answer)

    def drop_all(self) -> None:
        self.dropped.append(True)


@dataclass
class _Clock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


def _sync(job: Callable[[], None]) -> None:
    job()


def _lookup(monkeypatch: pytest.MonkeyPatch, bench: _Bench, **kwargs: Any) -> VoiceLookup:
    monkeypatch.setattr("web.voice_lookup.Bench", bench)
    monkeypatch.setattr("web.voice_lookup.native_picture", lambda *_a: None)
    engines = FakeTorrentEngines(FakeTorrentEngine())
    return VoiceLookup(engines=engines, **kwargs)


def test_a_slow_build_answers_nothing_yet_and_says_it_is_still_coming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = _lookup(monkeypatch, _Bench(_MEDIA), spawn=lambda _job: None)

    assert lookup.of(_PLAN, "film", "http://ts") == (None, True)


def test_the_tracks_of_the_resolved_release_come_back_and_the_bench_is_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    heard, coming = lookup.of(_PLAN, "film 2010", "http://ts")

    assert coming is False
    assert heard is not None
    assert heard.media.tracks == _MEDIA.tracks
    assert bench.asked[0][1].title_query == "film 2010"
    assert bench.dropped == [True]
    lookup.of(_PLAN, "film 2010", "http://ts")
    assert len(bench.asked) == 1


def test_a_refused_release_is_an_empty_answer_until_the_retry_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    bench = _Bench(InfraError("no fit"))
    lookup = _lookup(monkeypatch, bench, spawn=_sync, clock=clock)

    assert lookup.of(_PLAN, "film", "http://ts") == (None, False)
    assert bench.dropped == [True]
    lookup.of(_PLAN, "film", "http://ts")
    assert len(bench.asked) == 1

    clock.now += RETRY + 1
    bench.answer = _MEDIA
    heard, _coming = lookup.of(_PLAN, "film", "http://ts")

    assert heard is not None
    assert len(bench.asked) == 2
