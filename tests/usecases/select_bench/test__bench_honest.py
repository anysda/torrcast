"""Зеркало проверки честности: подтверждённое разрешение против обещанного именем."""

from __future__ import annotations

import threading
import time

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.media import Media
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки проверки честности верха отбора."""


_ASKED = Args(query=["кино"])
_RUS = (AudioTrack(index=0, language="rus"),)


def _media(height: int, width: int) -> Media:
    return Media(RUNTIME, _RUS, "h264", height=height, width=width)


def test_a_top_that_lied_about_its_frame_gives_way_to_an_honest_neighbour(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Живой случай: верх обещает 1080p, а внутри 574p, и рядом стоит настоящий."""
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    bench = Bench(
        Torrents(), prober=probes(pool, _media(574, 1150), _media(1080, 1920)), honest_budget=5.0
    )
    built = plan(pool)
    chosen = bench.start(built, 1)
    bench._wait(chosen, Said())

    played = bench._honest(built, chosen, [1, 2], _ASKED, Said())

    assert played.number == 2
    assert "беру 2" in capsys.readouterr().out


def test_an_honest_top_is_never_swapped(capsys: pytest.CaptureFixture[str]) -> None:
    """Верх не соврал - спрашивать соседей незачем, и ни строки об этом не печатается."""
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    bench = Bench(Torrents(), prober=probes(pool, _media(1080, 1920)), honest_budget=5.0)
    built = plan(pool)
    chosen = bench.start(built, 1)
    bench._wait(chosen, Said())

    played = bench._honest(built, chosen, [1, 2], _ASKED, Said())

    assert played is chosen
    assert capsys.readouterr().out == ""


def test_a_release_named_by_hand_is_never_checked() -> None:
    """``--release N`` - человек выбрал сам, и подменять его проверкой нечем."""
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    bench = Bench(Torrents(), prober=probes(pool, _media(574, 1150)), honest_budget=5.0)
    built = plan(pool)
    chosen = bench.start(built, 1)
    bench._wait(chosen, Said())

    assert bench._honest(built, chosen, [1], Args(query=["кино"], release=1), Said()) is chosen


def test_an_honest_neighbour_without_a_proven_voice_stays_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Честный 1080p без подтверждённой русской дорожки - не улучшение: подмена молчком
    выиграла бы разрешение, но подсунула бы зрителю картину без языка, который он попросил.
    """
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    silent = Media(RUNTIME, (AudioTrack(index=0, language="eng"),), "h264", height=1080, width=1920)
    bench = Bench(Torrents(), prober=probes(pool, _media(574, 1150), silent), honest_budget=5.0)
    built = plan(pool)
    chosen = bench.start(built, 1)
    bench._wait(chosen, Said())

    played = bench._honest(built, chosen, [1, 2], _ASKED, Said())

    assert played is chosen, "без честной дорожки подмена всё равно не должна была случиться"
    assert phrase("select_bench.honest_no_voice_note", number=2) in capsys.readouterr().out


def test_a_neighbour_already_judged_is_not_asked_twice(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-194. Приговорённого очередью не переспрашивают: вторая строка была бы враньём."""
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    bench = Bench(
        Torrents(), prober=probes(pool, _media(574, 1150), _media(1080, 1920)), honest_budget=5.0
    )
    built = plan(pool)
    chosen = bench.start(built, 1)
    bench._wait(chosen, Said())

    played = bench._honest(built, chosen, [1, 2], _ASKED, Said(), judged={2: "тяжелее потолка"})

    assert played is chosen
    assert "честнее рядом нет" in capsys.readouterr().out


def test_a_top_taken_by_the_deadline_asks_no_unread_neighbour() -> None:
    """Срок уже вышел: 384p «Призрака» ждал трёх соседей 12 с, кадр встал на 15.6 с."""
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    prober = probes(pool, _media(574, 1150), _media(1080, 1920))
    bench = Bench(Torrents(), prober=prober, honest_budget=5.0)
    built = plan(pool)
    chosen = bench.start(built, 1)
    bench._wait(chosen, Said())
    chosen.hurried = True

    played = bench._honest(built, chosen, [1, 2], _ASKED, Said())

    assert played is chosen
    assert (built.picture.key, 2) not in bench.preps, "соседа ради проверки не заводят"


def test_a_top_taken_by_the_deadline_still_gives_way_to_a_read_honest_neighbour() -> None:
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    prober = probes(pool, _media(574, 1150), _media(1080, 1920))
    bench = Bench(Torrents(), prober=prober, honest_budget=5.0)
    built = plan(pool)
    chosen, ready = bench.start(built, 1), bench.start(built, 2)
    bench._wait(chosen, Said())
    bench._wait(ready, Said())
    chosen.hurried = True

    assert bench._honest(built, chosen, [1, 2], _ASKED, Said()).number == 2


@pytest.mark.machine
def test_a_neighbour_that_did_not_answer_is_not_waited_for_again_on_the_same_bench() -> None:
    """🔴 «Во все тяжкие»: карточка ждала №3 весь бюджет и сыграла 400p, а показ на её
    стенде спросил №3 заново и ждал его ещё 8 с."""
    pool = [rel(name="r0 | Дубляж", seeders=140), rel(name="r1 | Дубляж", seeders=121)]
    read, gone, asked = probes(pool, _media(400, 720), _media(1080, 1920)), threading.Event(), []

    def prober(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{pool[1].magnet}/" in source_url:
            asked.append(source_url)
            gone.wait(30.0)
        return read(source_url, timeout=timeout)

    bench = Bench(Torrents(), prober=prober, honest_budget=0.5)
    built = plan(pool)
    chosen = bench.start(built, 1)
    bench._wait(chosen, Said())
    try:
        assert bench._honest(built, chosen, [1, 2], _ASKED, Said()) is chosen
        began = time.monotonic()

        played = bench._honest(built, chosen, [1, 2], _ASKED, Said())

        assert played is chosen
        assert time.monotonic() - began < 0.3
        assert len(asked) == 1, "прожданного соседа второй раз не спрашивают"
    finally:
        gone.set()
