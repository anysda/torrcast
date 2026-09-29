"""Срок отбора нового показа: после него готовая годная младшая раздача не ждёт старшую."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace

import pytest

import torrcast.usecases.select_bench._bench_in_time as _bench_in_time
from tests.fakes import composition
from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.swarm_error import SwarmError
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
    bench = Bench(Torrents(), prober=_prober(top_answers, 1.2, _RUS, _ENG, _ENG))

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_judged_spare_hands_the_deadline_to_the_next_release_in_the_queue(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 №2 осуждён, №3 годен: после срока играет №3, а не молчащий №1 до конца терпения.

    «Призрак в доспехах» ждал молчащий №1 20 с при №2 без русского звука.
    """
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.4)
    bench = Bench(Torrents(), prober=_prober(top_answers, 30.0, _RUS, _ENG, _RUS))
    began = time.monotonic()

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 3
    assert time.monotonic() - began < 3.0


@pytest.mark.machine
def test_a_younger_release_that_the_receiver_gets_recoded_does_not_jump_the_queue(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """Младшая тяжелее потолка приёмника пережимается на ходу и срока не выигрывает."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    heavy = replace(_RUS, video_bps=15_000_000.0)
    bench = Bench(Torrents(), prober=_prober(top_answers, 1.2, _RUS, heavy, heavy))

    prep = bench.resolve(plan(_POOL, recode_at=10.0), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_younger_release_of_another_year_does_not_jump_the_queue(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 Склеенная соседняя работа («Rick and Morty: The Anime» 2024 в картине 2013) не подмена."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    pool = [_POOL[0], replace(_POOL[1], year=2024), replace(_POOL[2], year=2024)]
    bench = Bench(Torrents(), prober=_prober(top_answers, 1.2, _RUS, _RUS))

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_younger_release_whose_keyframe_map_is_still_read_does_not_jump_the_queue(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """Без карты опорных кадров у подмены нет сетки, и LOAD ждал бы её: ждётся старшая."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    reading = threading.Event()
    taken = threading.Event()
    taken.set()

    def warm(source_url: str, **_: object) -> threading.Event:
        return reading if f"hash-{_POOL[1].magnet}/" in source_url else taken

    composition.use_warm_file(monkeypatch, warm)
    bench = Bench(Torrents(), prober=_prober(top_answers, 1.2, _RUS, _RUS, _ENG))

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_spare_still_read_after_the_deadline_does_not_hold_back_the_next_release(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 №2 ещё читается, №3 годен: после срока №3 греется и играет, а не ждёт №2.

    «Призрак в доспехах» - японский №2 на 40 ГБ читался 13.5 с, годный №3
    до того не грелся, кадр через 28.5 с.
    """
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    reading = threading.Event()
    taken = threading.Event()
    taken.set()

    def warm(source_url: str, **_: object) -> threading.Event:
        return reading if f"hash-{_POOL[1].magnet}/" in source_url else taken

    composition.use_warm_file(monkeypatch, warm)
    bench = Bench(Torrents(), prober=_prober(top_answers, 30.0, _RUS, _RUS, _RUS))
    began = time.monotonic()

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 3
    assert time.monotonic() - began < 3.0
    reading.set()


@pytest.mark.machine
def test_the_show_taking_a_card_bench_does_not_wait_the_top_out_again(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 Срок идёт с первого отбора картины на стенде: показ после карточки старшую заново не ждёт.

    Карточка на сроке взяла №2, показ, забрав её стенд, ждал №1 ещё 1.8 с
    и всё равно взял №2.
    """
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 1.0)
    bench = Bench(Torrents(), prober=_prober(top_answers, 30.0, _RUS, _RUS))
    assert bench.resolve(plan(_POOL), _ASKED, Said()).number == 2
    began = time.monotonic()

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 2
    assert time.monotonic() - began < 0.5


@pytest.mark.machine
def test_the_show_takes_the_release_the_card_read_while_it_waits_the_top_again(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 Карточка сняла молчащие №1 и №2 и дочитала №3: показ после срока берёт №3.

    «Во все тяжкие» - показ, забрав стенд карточки, завёл №1 и №2 заново,
    а готовый №3 стоял вне фронта, и кадр ждал заново заведённый №1 11 с.
    """
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    read = probes(_POOL, _RUS, _RUS, _RUS)
    silent: set[str] = set()

    def swarm(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        hashes = (f"hash-{release.magnet}/" for release in _POOL[:2])
        if (top := next((h for h in hashes if h in source_url), None)) is not None:
            if top not in silent:
                silent.add(top)
                raise SwarmError("рой молчит", waited=10.0)
            top_answers.wait(30.0)
        return read(source_url, timeout=timeout, alive=alive)

    bench = Bench(Torrents(), prober=swarm)
    assert bench.resolve(plan(_POOL), _ASKED, Said()).number == 3, "карточка дочитала №3"
    began = time.monotonic()

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 3
    assert time.monotonic() - began < 1.0


@pytest.mark.machine
def test_the_show_does_not_wait_again_for_a_swarm_the_card_waited_out(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 Карточка прождала молчащий №1 весь свой срок: показ его заново не ждёт.

    «Призрак в доспехах» - карточка ждала №1 20 с, показ завёл его заново и
    ждал ещё 10, а №3 (ТВ-2, другого года, подменой не берётся) стоял готовым.
    """
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    pool = [_POOL[0], _POOL[1], replace(_POOL[2], year=2004)]
    bench = Bench(Torrents(), prober=_prober(top_answers, 30.0, _RUS, _ENG, _RUS), pick_budget=1.0)
    with pytest.raises(NotFoundError):
        bench.resolve(plan(pool), _ASKED, Said())
    bench.pick_budget = 5.0
    began = time.monotonic()

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 3
    assert time.monotonic() - began < 1.5


@pytest.mark.machine
def test_a_recounted_circle_waits_for_its_new_top_though_the_card_waited_out_that_number(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 Прожданный рой помнится магнитом: номер у пересчитанного круга уже чужой.

    Опоздавший индексер пересчитал круг «Призрака» (30 раздач стало 40), и
    показ счёл бы прожданным новый №1 лишь за то, что карточка не дождалась старого.
    """
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    pool = [_POOL[0], _POOL[1], replace(_POOL[2], year=2004)]
    newcomer = rel(name="new | Дубляж", seeders=500)
    read = _prober(top_answers, 30.0, _RUS, _ENG, _RUS)

    def prober(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{newcomer.magnet}/" in source_url:
            time.sleep(0.5)
            return _RUS
        return read(source_url, timeout=timeout, alive=alive)

    bench = Bench(Torrents(), prober=prober, pick_budget=1.0)
    with pytest.raises(NotFoundError):
        bench.resolve(plan(pool), _ASKED, Said())
    bench.pick_budget = 5.0

    prep = bench.resolve(plan([newcomer, *pool]), _ASKED, Said())

    assert prep.release is newcomer


@pytest.mark.machine
def test_a_release_taken_by_the_deadline_does_not_wait_again_for_its_honesty(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """Взятый сроком 720p под именем 1080p не ждёт проверки честности: «Призрак» ждал 12 с."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.4)
    pool = [rel(name=f"r{n} 1080p | Дубляж", seeders=100 - n) for n in range(3)]
    small = replace(_RUS, height=720, width=1280)
    read = probes(pool, _RUS, small)

    def slow(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{pool[0].magnet}/" in source_url:
            top_answers.wait(30.0)
        return read(source_url, timeout=timeout, alive=alive)

    bench = Bench(Torrents(), prober=slow, honest_budget=5.0)
    began = time.monotonic()

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert (prep.number, prep.hurried) == (2, True)
    assert time.monotonic() - began < 3.0


@pytest.mark.machine
def test_a_younger_release_below_hd_does_not_jump_the_queue(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """«HDRip» «Рататуя» оказался 288p: срок его не берёт, играет старшая в свой черёд."""
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    sd = replace(_RUS, height=288, width=512)
    bench = Bench(Torrents(), prober=_prober(top_answers, 1.2, _RUS, sd, sd))

    prep = bench.resolve(plan(_POOL), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_spare_read_and_found_unfit_leaves_its_place_in_the_front(
    monkeypatch: pytest.MonkeyPatch, top_answers: threading.Event
) -> None:
    """🔴 №2 без русского звука дочитан, №3 ещё читается: греется и играет №4.

    Японский №2 «Призрака» держал место во фронте, русский №5 карточка не завела
    за 20 с, и показ сыграл японский звук.
    """
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(4)]
    read = probes(pool, _RUS, _ENG, _RUS, _RUS)
    silent = {f"hash-{pool[n].magnet}/" for n in (0, 2)}

    def slow(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if any(part in source_url for part in silent):
            top_answers.wait(30.0)
        return read(source_url, timeout=timeout, alive=alive)

    bench = Bench(Torrents(), prober=slow)
    began = time.monotonic()

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 4
    assert time.monotonic() - began < 3.0
