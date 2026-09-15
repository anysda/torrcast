"""Срок отбора нового показа: после него готовая годная младшая раздача не ждёт старшую."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator

import pytest

import torrcast.usecases.select_bench._bench_in_time as _bench_in_time
from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - отбор под русской ручкой: годна подтверждённая русская дорожка."""


_ASKED = Args(query=["кино"])
_RUS = Media(RUNTIME, (AudioTrack(index=0, language="rus"),), "h264", height=1080, width=1920)
_ENG = Media(RUNTIME, (AudioTrack(index=0, language="eng"),), "h264", height=1080, width=1920)
_POOL = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(3)]


@pytest.fixture
def top_answers() -> Iterator[threading.Event]:
    """Старшая раздача отвечает, только когда тест разрешит; в конце разрешается всегда."""
    event = threading.Event()
    yield event
    event.set()


def _prober(top: threading.Event, top_delay: float, *media: Media) -> Callable[..., Media]:
    read = probes(_POOL, *media)

    def slow(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{_POOL[0].magnet}/" in source_url:
            top.wait(top_delay)
        return read(source_url, timeout=timeout, alive=alive)

    return slow


@pytest.mark.machine
def test_a_fit_younger_release_plays_once_the_top_misses_the_deadline(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 Старшая молчит дольше срока, младшая годна и готова: играет младшая, в срок."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.4)
    bench = Bench(Torrents(), prober=_prober(top_answers, 30.0, _RUS, _RUS))
    began = time.monotonic()

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 2
    assert time.monotonic() - began < 3.0


@pytest.mark.machine
def test_the_top_that_answers_before_the_deadline_plays_though_a_younger_was_ready_first(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """Порядок очереди не меняется: до срока ждётся лучшая, даже если младшая уже готова."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 3.0)
    bench = Bench(Torrents(), prober=_prober(top_answers, 0.6, _RUS, _RUS))

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_younger_release_without_a_proven_russian_track_does_not_jump_the_queue(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """Гейт TC-492 цел: младшая с английским звуком после срока старшую не подменяет."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    bench = Bench(Torrents(), prober=_prober(top_answers, 1.2, _RUS, _ENG))

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 1
