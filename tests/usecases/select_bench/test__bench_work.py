"""Зеркало фоновой подготовки: раздача, метаданные, дорожки - и как их ждут."""

from __future__ import annotations

from itertools import count

from tests.fakes.clock import FakeClock
from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.domain.media import Media
from torrcast.domain.swarm_error import SwarmError
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench.bench import Bench


def test_a_healthy_release_is_prepared_whole_in_the_background() -> None:
    """Раздача, файл и паспорт - всё это фоновая работа, а показ спрашивает результат."""
    one = rel()
    bench = Bench(Torrents(), prober=probes([one], Media(RUNTIME, (), "h264")))

    prep = bench.start(plan([one]), 1)
    bench._wait(prep, Said())

    assert prep.phase == "готово"
    assert prep.found.video == "h264"
    assert prep.want.name == "movie.mkv"


def test_a_swarm_that_never_answered_is_a_failure_of_its_own_type() -> None:
    """Молчание роя опознаётся ТИПОМ отказа, а не префиксом текста."""
    one = rel()
    torrents = Torrents(dead={f"hash-{one.magnet}"})
    bench = Bench(torrents, prober=probes([one]), meta_budget=0.5)

    prep = bench.start(plan([one]), 1)
    bench._wait(prep, Said())

    assert prep.phase == "сбой"
    assert isinstance(prep.failure, SwarmError)
    assert "нет пиров" in prep.error


def test_peeking_at_a_neighbour_never_makes_it_unfit() -> None:
    """Срок подглядывания наш, а не релиза: просроченному прогреву отказа не ставится."""
    bench = Bench(Torrents(), prober=probes([]), clock=lambda: 1e9)
    slow = _Prep(number=1, release=rel())

    assert bench._peek(slow, Said(), deadline=0.0, phase="смотрю") is False
    assert slow.error == "", "подглядывание за соседом не делает его негодным"


def test_our_own_waiting_that_ran_out_is_named_as_ours() -> None:
    """Поток сам не уложился - ждать вечно нельзя, и строка называет фазу."""
    bench = Bench(Torrents(), prober=probes([]), clock=lambda: 1e9)
    slow = _Prep(number=1, release=rel())
    slow.phase = "дорожки"

    bench._wait(slow, Said())

    assert slow.error == "фаза «дорожки» не уложилась в бюджет"


def test_a_warm_up_counts_its_own_budget_from_the_moment_it_started() -> None:
    """Свой срок прогрев отсчитывает от начала работы, а не от вопроса к нему.

    Часы стенда идут по секунде на взгляд, поэтому счёт показанных фаз - это и есть
    счёт секунд, которые ожидание себе взяло.
    """
    ticks = count(101.0)
    bench = Bench(
        Torrents(), prober=probes([]), meta_budget=1.0, probe_budget=1.0, clock=lambda: next(ticks)
    )
    late = _Prep(number=1, release=rel(), contact_wait=ContactWait(6.0, FakeClock(now=100.0)))
    late.started = 0.0  # прогрев начал работу сто секунд назад
    late.contact_wait.activate(6.0)  # type: ignore[union-attr]
    said = Said()

    bench._wait(late, said)

    assert late.error == "фаза «очередь» не уложилась в бюджет"
    assert len(said.phases) == 1, "срок прогрева вышел ещё до вопроса - ждать нечего"
