"""Зеркало проверки честности: подтверждённое разрешение против обещанного именем."""

from __future__ import annotations

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
