"""VoiceLookup: отбор раздачи в фоне, кэш на процесс, прогретое убрано за собой."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

import web.card_warm
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.fakes.torrent_engines import FakeTorrentEngines
from tests.usecases.rank.releases import media, track
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.episode_lookup import RETRY
from web.voice_lookup import VoiceLookup

_RELEASE = Release(raw_name="Film 2010 BDRip 1080p LostFilm", title="Film", magnet="magnet:f")
_PICTURE = Picture(title="Film", year=2010, kind="movie", releases=[_RELEASE])
_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE], runtime=0, warn_mbit=0)
_CONFIG = Config(torrserver_url="http://ts", receiver_profile="q70d")
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
    kept: list[Any] = field(default_factory=list)
    asked: list[tuple[Plan, Any]] = field(default_factory=list)

    profiles: list[Any] = field(default_factory=list)
    release: Release = _RELEASE

    def __call__(self, _engine: object, choose: object = None, profile: Any = None) -> _Bench:
        self.profiles.append(profile)
        return self

    def resolve(self, plan: Plan, args: Any, _progress: object) -> _Prep:
        self.asked.append((plan, args))
        if isinstance(self.answer, Exception):
            raise self.answer
        return _Prep(self.answer, self.release)

    def drop_all(self) -> None:
        self.dropped.append(True)

    def keep_only(self, prep: Any) -> None:
        self.kept.append(prep)


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

    assert lookup.of(_PLAN, "film", _CONFIG) == (None, True)


def test_the_tracks_come_back_and_only_the_chosen_release_stays_warm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    heard, coming = lookup.of(_PLAN, "film 2010", _CONFIG)

    assert coming is False
    assert heard is not None
    assert heard.media.tracks == _MEDIA.tracks
    assert bench.asked[0][1].title_query == "film 2010"
    assert [profile.key for profile in bench.profiles] == ["q70d"], "судит профилем показа"
    assert [prep.found for prep in bench.kept] == [_MEDIA] and bench.dropped == []
    lookup.of(_PLAN, "film 2010", _CONFIG)
    assert len(bench.asked) == 1


def test_a_card_opened_again_warms_the_release_it_already_chose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)
    heard, _coming = lookup.of(_PLAN, "film", _CONFIG)
    assert heard is not None

    lookup.warms.leave(_PLAN.picture.key)
    again, coming = lookup.of(_PLAN, "film", _CONFIG)

    assert bench.dropped == [True], "ушла карточка - ушёл и прогрев"
    assert again is heard and coming is False
    assert len(bench.asked) == 2
    assert bench.asked[1][1].card_release == heard.release


def test_a_refused_release_is_an_empty_answer_until_the_retry_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    bench = _Bench(InfraError("no fit"))
    lookup = _lookup(monkeypatch, bench, spawn=_sync, clock=clock)

    assert lookup.of(_PLAN, "film", _CONFIG) == (None, False)
    assert bench.dropped == [True] and bench.kept == []
    lookup.of(_PLAN, "film", _CONFIG)
    assert len(bench.asked) == 1

    clock.now += RETRY + 1
    bench.answer = _MEDIA
    heard, _coming = lookup.of(_PLAN, "film", _CONFIG)

    assert heard is not None
    assert len(bench.asked) == 2


_KEPT = Release(raw_name="Film 2010 1080p", title="Film", magnet="magnet:?xt=urn:btih:" + "a" * 40)
_KEPT_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE, _KEPT], runtime=0, warn_mbit=0)


def _live(**rest: Any) -> Entry:
    return Entry(**{"title": "Film", "magnet": _KEPT.magnet, "dur": 7200.0, "pos": 180.0, **rest})


def test_a_live_bookmark_card_lists_the_tracks_of_the_bookmark_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Играть продолжит закладку - меню, отметка и прогрев принадлежат её раздаче."""
    bench = _Bench(_MEDIA, release=_KEPT)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    heard, _coming = lookup.of(_KEPT_PLAN, "film", _CONFIG, _live())

    assert bench.asked[0][1].card_release == "a" * 40
    assert heard is not None and heard.release == "a" * 40


def test_a_card_picked_before_the_bookmark_is_picked_again_for_the_bookmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)
    first, _coming = lookup.of(_KEPT_PLAN, "film", _CONFIG)
    assert first is not None and first.release != "a" * 40

    lookup.warms.leave(_PICTURE.key)
    bench.release = _KEPT
    heard, _coming = lookup.of(_KEPT_PLAN, "film", _CONFIG, _live())

    assert [asked[1].card_release for asked in bench.asked] == ["", "a" * 40]
    assert heard is not None and heard.release == "a" * 40


def test_tracks_of_another_release_are_not_passed_off_as_the_bookmark_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отбор не взял раздачу закладки - меню нет: чужие дорожки соврали бы."""
    lookup = _lookup(monkeypatch, _Bench(_MEDIA), spawn=_sync)

    assert lookup.of(_KEPT_PLAN, "film", _CONFIG, _live()) == (None, False)


def test_a_show_bookmark_warms_its_own_episode_and_a_finished_film_does_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA, release=_KEPT)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)
    show = _live(kind="tv", season=2, episode=5, pos=0.0, episodes=[[2, 4, 0], [2, 5, 1]])

    lookup.of(_KEPT_PLAN, "film", _CONFIG, show)
    other = Picture(title="Other", year=2011, kind="movie", releases=[_RELEASE])
    lookup.of(
        Plan(picture=other, ranked=[_RELEASE], runtime=0, warn_mbit=0),
        "o",
        _CONFIG,
        _live(done=True),
    )

    episode = bench.asked[0][1].episode
    assert (episode.season, episode.episode) == (2, 5)
    assert bench.asked[1][1].card_release == ""


def test_a_release_other_than_the_bookmark_one_is_not_left_warm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Играть продолжит закладку: чужую раздачу, взятую отбором карточки, держать незачем."""
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    lookup.of(_KEPT_PLAN, "film", _CONFIG, _live())

    assert bench.kept == [] and bench.dropped == [True]
    assert not lookup.warms.holds(_PICTURE.key)


@dataclass
class _Choosing(_Bench):
    """Отбор карточки, который идёт, пока его не снимут: спрашивает индикатор по кругу."""

    profile: Any = None
    choose: Any = None
    preps: dict[Any, Any] = field(default_factory=dict)
    entered: threading.Event = field(default_factory=threading.Event)

    def resolve(self, plan: Plan, args: Any, progress: Any) -> _Prep:
        self.asked.append((plan, args))
        self.entered.set()
        while True:
            progress.phase("метаданные")
            time.sleep(0.01)


@pytest.mark.machine
def test_a_show_clicked_while_the_card_chooses_gets_the_card_bench_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Снятый показом отбор карточки отпускает стенд сразу, а ответ ждёт уже от показа.

    Раньше карточка ждала ответа показа, не отпустив стенд, а показ ждал стенд: оба
    стояли весь ``LET_GO``, и показ уходил отбирать заново рядом с греющимся стендом.
    """
    monkeypatch.setattr(web.card_warm, "LET_GO", 3.0)
    bench = _Choosing(_MEDIA)
    threads: list[threading.Thread] = []

    def spawn(job: Callable[[], None]) -> None:
        threads.append(threading.Thread(target=job, daemon=True))
        threads[-1].start()

    lookup = _lookup(monkeypatch, bench, spawn=spawn)
    lookup.of(_PLAN, "film", _CONFIG)
    assert bench.entered.wait(5.0)

    began = time.monotonic()
    fresh: Any = _Choosing(_MEDIA)
    got: Any = lookup.warms.take(_PICTURE.key, fresh)
    waited = time.monotonic() - began

    assert got is bench, f"показ отбирал бы вторым стендом после {waited:.2f} с"
    assert waited < 1.0
    ready: Any = _Prep(_MEDIA)
    lookup.warms.settled(cast(Any, got), ready)
    threads[0].join(5.0)
    lookup.spawn = lambda _job: None  # карточка открыта заново: прогрев уже не про этот тест
    assert lookup.of(_PLAN, "film", _CONFIG)[0] is not None, "дорожки - от раздачи показа"
    assert bench.dropped == [] and bench.kept == [], "стенд у показа: карточка его не трогает"
