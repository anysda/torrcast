"""Зеркало обхода очереди отбора: годный релиз, а на осечке - строка и следующий."""

from __future__ import annotations

import time

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.select_bench.bench import Bench

_ASKED = Args(query=["кино"])
_RUS = (AudioTrack(index=0, language="rus"),)


def _media(codec: str = "h264") -> Media:
    return Media(RUNTIME, _RUS, codec, height=1080, width=1920)


def test_the_first_fit_release_is_the_answer() -> None:
    """Счастливый путь: верх очереди годен, и дальше него отбор не идёт."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    bench = Bench(Torrents(), prober=probes(pool, _media(), _media()))

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1


def test_an_unfit_top_is_swapped_out_loud(capsys: pytest.CaptureFixture[str]) -> None:
    """Молчаливых подмен не бывает: каждая осечка стоит строки и следующего кандидата."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    bench = Bench(Torrents(), prober=probes(pool, _media("av1"), _media()))

    prep = bench.resolve(plan(pool, recode_at=0.0), _ASKED, Said())

    assert prep.number == 2
    assert "релиз 1 не годится (av1) - беру 2" in capsys.readouterr().out


def test_a_queue_of_nothing_but_verdicts_ends_with_an_honest_refusal() -> None:
    """Все до одного прочитаны и осуждены - это отказ отбора, а не молчание роя."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    bench = Bench(Torrents(), prober=probes(pool, _media("av1"), _media("vp9")))

    with pytest.raises(NotFoundError, match="годного релиза нет"):
        bench.resolve(plan(pool, recode_at=0.0), _ASKED, Said())


def test_a_queue_that_only_kept_silent_names_the_swarm_not_the_choice() -> None:
    """🔴 TC-435. Ни одного приговора - врать «годного релиза нет» тут нельзя."""
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    dead = {f"hash-{one.magnet}" for one in pool}
    bench = Bench(Torrents(dead=dead), prober=probes(pool), meta_budget=0.5, probe_budget=0.5)

    with pytest.raises(NotFoundError, match="раздач в выдаче 2"):
        bench.resolve(plan(pool), _ASKED, Said())


def test_a_release_without_russian_waits_and_plays_when_nobody_has_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-178. Человек без картины не остаётся: гейт озвучки не слепой."""
    pool = [rel(name="r0 | Дубляж", seeders=100)]
    japanese = Media(
        RUNTIME, (AudioTrack(index=0, language="jpn"),), "h264", height=1080, width=1920
    )
    bench = Bench(Torrents(), prober=probes(pool, japanese))

    prep = bench.resolve(plan(pool), _ASKED, Said())

    assert prep.number == 1
    assert "русской озвучки нет ни в одной из проверенных раздач" in capsys.readouterr().out


@pytest.mark.machine
def test_the_hunt_for_a_russian_track_names_the_release_it_is_waiting_for() -> None:
    """Пока идёт спрос, бегущая строка называет, ЧЬЮ озвучку ищут: релиз N из M.

    Строка эта видна только на непрогретой раздаче: прогретая под меню отвечает
    мгновенно, и фазу спрашивать не у кого. Поэтому паспорт тут едет не сразу, а
    запасной - ещё и дольше верха: греется-то он с ним наперегонки.
    """
    pool = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(2)]
    read = probes(pool, _media("av1"), _media())
    said = Said()

    def slow(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        # Дольше шага опроса фазы (:meth:`Bench._wait`), иначе спрашивать нечего.
        time.sleep(0.3 if f"hash-{pool[0].magnet}/" in source_url else 0.9)
        return read(source_url, timeout=timeout, alive=alive)

    bench = Bench(Torrents(), prober=slow)

    prep = bench.resolve(plan(pool, recode_at=0.0), _ASKED, said)

    assert prep.number == 2, "верх осуждён по кодеку - спрашивали обоих"
    asked = {phase.rsplit(" - ", 1)[0] for phase in said.phases if phase.startswith("ищу русскую")}
    assert asked == {
        "ищу русскую озвучку: релиз 1 из 2",
        "ищу русскую озвучку: релиз 2 из 2",
    }
