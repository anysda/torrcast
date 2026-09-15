"""Зеркало фоновой подготовки: раздача, метаданные, дорожки - и как их ждут."""

from __future__ import annotations

import threading
from itertools import count

import pytest

from tests.fakes.clock import FakeClock
from tests.usecases.select_bench.world import GB, RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские фазы фоновой подготовки релиза."""


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


def test_a_renumbered_pool_does_not_hand_over_the_warm_up_of_another_release() -> None:
    """🔴 Карточка грела номер 1 одного круга, показ пересчитал круг, и номер 1 стал другим."""
    first, second = rel("Кино / Movie (1999) BDRip 1080p"), rel("Кино / Movie (1999) WEB 720p")
    bench = Bench(Torrents(), prober=probes([first, second]))
    old = bench.start(plan([first, second]), 1)
    bench._wait(old, Said())

    fresh = bench.start(plan([second, first]), 1)

    assert fresh.release.magnet == second.magnet
    assert old.dropped


def test_a_warm_up_already_dropped_is_not_handed_to_the_show() -> None:
    """🔴 Закладка снесла прогретое под меню, её раздача мертва, и отбор взял снесённое: 404."""
    one = rel()
    bench = Bench(Torrents(), prober=probes([one]))
    old = bench.start(plan([one]), 1)
    bench._wait(old, Said())
    bench.drop_all()

    fresh = bench.start(plan([one]), 1)
    bench._wait(fresh, Said())

    assert fresh is not old
    assert not fresh.dropped and not fresh.error
    assert bench.live() == [fresh]


class _SlowAdd(Torrents):
    """Второй ``add`` той же раздачи висит, пока его не отпустят: занятый TorrServer."""

    def __init__(self) -> None:
        super().__init__()
        self.adds, self.adding, self.let = 0, threading.Event(), threading.Event()

    def add(self, magnet: str) -> str:
        self.adds += 1
        if self.adds == 2:
            self.adding.set()
            self.let.wait(5)
        return super().add(magnet)


def test_a_dropped_warm_up_ending_late_does_not_drop_the_fresh_one_still_adding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Снесённый прогрев кончился, пока свежий той же раздачи ждал ``add``: снос его торрента."""
    one, torrents, probing, done = rel(), _SlowAdd(), threading.Event(), threading.Event()

    def prober(_source: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        probing.set()
        done.wait(5)
        return Media(RUNTIME, (), "h264")

    bench = Bench(torrents, prober=prober)
    old = bench.start(plan([one]), 1)
    assert probing.wait(5)
    bench.drop_all()
    forgot, forget = threading.Event(), bench._forget

    def forgetting(prep: _Prep) -> None:
        forget(prep)
        forgot.set()

    monkeypatch.setattr(bench, "_forget", forgetting)
    fresh = bench.start(plan([one]), 1)
    assert torrents.adding.wait(5)
    done.set()
    assert forgot.wait(5) and old.dropped
    torrents.let.set()
    bench._wait(fresh, Said())

    assert torrents.dropped == [f"hash-{one.magnet}"], "свежий прогрев потерял раздачу"
    assert not fresh.error and bench.live() == [fresh]


def test_a_fresh_warm_up_whose_add_failed_does_not_keep_the_old_torrent() -> None:
    """Свежий прогрев той же раздачи упал на ``add``: снесённый старый уносит свою раздачу."""
    one, torrents = rel(), Torrents()
    bench = Bench(torrents, prober=probes([one]))
    old, failed = _Prep(number=1, release=one), _Prep(number=1, release=one)
    old.torrent_hash = f"hash-{one.magnet}"
    failed.ready.set()
    bench.preps = {("old", 1): old, ("fresh", 1): failed}

    bench._forget(old)

    assert torrents.dropped == [f"hash-{one.magnet}"]


def test_a_nameless_sound_file_in_a_russian_folder_is_the_russian_voice() -> None:
    """Безымянный .mka в «Sound/Rus [Dub+MVO]» - русская дорожка, и серия не играет японской."""
    pool = [rel(name="Наруто (S1) [RUS(ext), ENG, JAP+Sub]", seeders=91)]
    root = "[SOFCJ-Raws] Naruto (DVDRip)"
    files = [
        TorrFile(0, f"{root}/[SOFCJ-Raws] Naruto - 111 (DVDRip).mkv", GB),
        TorrFile(
            1, f"{root}/Sound/Rus [Dub+MVO]/[2x2] [MVO]/[SOFCJ-Raws] Naruto - 111 (DVDRip).mka"
        ),
    ]
    japanese = Media(RUNTIME, (AudioTrack(index=0, language="jpn"),), "hevc", height=576)
    nameless = Media(RUNTIME, (AudioTrack(index=0, codec="ac3"),), None)

    def read(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        return nameless if source_url.endswith("/1") else japanese

    prep = Bench(Torrents(files=files), prober=read).resolve(
        plan(pool), Args(query=["Наруто"]), Said()
    )

    assert prep.apart, "русская дорожка из каталога Rus не опознана: серия пойдёт по-японски"
    assert prep.voiced is not None and prep.voiced.russian
