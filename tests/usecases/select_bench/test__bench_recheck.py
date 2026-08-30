"""Зеркало второго спроса: очередь промолчала целиком - лучший спрашивается ещё раз."""

from __future__ import annotations

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки второго спроса промолчавшей очереди."""


_ASKED = Args(query=["кино"])
_RUS = (AudioTrack(index=0, language="rus"),)


def test_a_swarm_that_only_seemed_dead_plays_on_the_second_ask(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-300. Живой рой, которого не дождались, выглядит точно так же, как мёртвый."""
    pool = [rel(name="r0 | Дубляж", seeders=100)]
    built = plan(pool)
    torrents = Torrents()
    bench = Bench(
        torrents,
        prober=probes(pool, Media(RUNTIME, _RUS, "h264", height=1080, width=1920)),
        meta_budget=1.0,
        probe_budget=1.0,
    )
    silent = bench.start(built, 1)
    bench._wait(silent, Said())
    silent.media = None
    silent.error = "раздача не отдала метаданные за 1 с - нет пиров"

    revived = bench._recheck(built, [1], _ASKED, Said(), {}, deadline=bench.clock() + 100.0)

    assert revived is not None and revived.number == 1
    assert "спрашиваю релиз 1 ещё раз, одного и без отсрочек" in capsys.readouterr().out


def test_a_queue_whose_releases_answered_for_themselves_is_not_asked_again() -> None:
    """Раздачу без нужной серии терпение не изменит - второго спроса ей не бывает."""
    pool = [rel(name="r0 | Дубляж", seeders=100)]
    built = plan(pool)
    bench = Bench(Torrents(), prober=probes(pool))
    known = bench.start(built, 1)
    bench._wait(known, Said())

    assert bench._recheck(built, [1], _ASKED, Said(), {}, deadline=bench.clock() + 100.0) is None


def test_the_second_ask_never_takes_the_phase_past_its_ceiling() -> None:
    """Честный второй спрос в остаток бюджета фазы уже не влезает - его и не бывает."""
    pool = [rel(name="r0 | Дубляж", seeders=100)]
    built = plan(pool)
    bench = Bench(Torrents(), prober=probes(pool), meta_budget=30.0, probe_budget=30.0)
    silent = bench.start(built, 1)
    bench._wait(silent, Said())
    silent.media = None
    silent.error = "раздача не отдала метаданные - нет пиров"

    assert bench._recheck(built, [1], _ASKED, Said(), {}, deadline=bench.clock() + 1.0) is None


def test_a_revived_release_whose_language_is_unnamed_does_not_play(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-741. Второй спрос оживил раздачу, а язык её звука так и не назван - не играем.

    Правило тут ровно то же, что в обходе очереди: подтверждённый русский - годен,
    названный чужой - последний ход с честной строкой, а незнание не ход вовсе. Прежде
    ожившая безымянная раздача уезжала запасным ходом под строку «звук не назван», то
    есть терпение покупало зрителю ровно то, чего гейт и не пропускал.
    """
    pool = [rel(name="r0 | Дубляж", seeders=100)]
    built = plan(pool)
    unnamed = Media(RUNTIME, (AudioTrack(index=0),), "h264", height=1080, width=1920)
    bench = Bench(Torrents(), prober=probes(pool, unnamed), meta_budget=1.0, probe_budget=1.0)
    silent = bench.start(built, 1)
    bench._wait(silent, Said())
    silent.media = None
    silent.error = "раздача не отдала метаданные за 1 с - нет пиров"

    revived = bench._recheck(built, [1], _ASKED, Said(), {}, deadline=bench.clock() + 100.0)

    printed = capsys.readouterr().out
    assert revived is None, "незнание запасным ходом не становится и на втором спросе"
    assert "релиз 1 ответил в одиночку, но без русской озвучки" in printed
    assert "включаю релиз" not in printed


def test_a_revived_release_whose_language_is_named_still_plays(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Отрицательная половина: срезает второй спрос именно незнание, а не чужой язык."""
    pool = [rel(name="r0 | Дубляж", seeders=100)]
    built = plan(pool)
    japanese = Media(
        RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920
    )
    bench = Bench(Torrents(), prober=probes(pool, japanese), meta_budget=1.0, probe_budget=1.0)
    silent = bench.start(built, 1)
    bench._wait(silent, Said())
    silent.media = None
    silent.error = "раздача не отдала метаданные за 1 с - нет пиров"

    revived = bench._recheck(built, [1], _ASKED, Said(), {}, deadline=bench.clock() + 100.0)

    assert revived is not None and revived.number == 1
    assert "включаю релиз 1, звук японский" in capsys.readouterr().out
