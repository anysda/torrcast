"""Наследник безмолвной раздачи: тяжёлый следующий по очереди не ждёт, пока она истечёт."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace

import pytest

import torrcast.usecases.select_bench._bench_heir as _bench_heir
import torrcast.usecases.select_bench._bench_in_time as _bench_in_time
from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.contact_wait import ContactWait
from torrcast.ports.json_value import JsonValue
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - отбор под русской ручкой: годна подтверждённая русская дорожка."""


_ASKED = Args(query=["кино"])
_RUS = Media(RUNTIME, (AudioTrack(index=0, language="rus"),), "h264", height=1080, width=1920)
_ENG = Media(RUNTIME, (AudioTrack(index=0, language="eng"),), "h264", height=1080, width=1920)
_HEAVY = replace(_RUS, video_bps=15_000_000.0)
_POOL = [rel(name=f"r{n} | Дубляж", seeders=100 - n) for n in range(3)]
#: Бюджет метаданных стенда в зеркале: столько отбор ждал бы безмолвный №1 без наследника.
_META = 4.0


class _Mute(Torrents):
    """Служба раздач, у которой верх ранжира метаданных не отдаёт до конца бюджета."""

    def __init__(self, released: threading.Event) -> None:
        super().__init__()
        self.released = released

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float | ContactWait = 0.0
    ) -> list[TorrFile]:
        if torrent_hash == f"hash-{_POOL[0].magnet}":
            self.released.wait(timeout)
            raise SwarmError(f"раздача не отдала метаданные за {timeout:.0f} с")
        return super().wait_files(torrent_hash, timeout, grace)


@pytest.fixture
def released() -> Iterator[threading.Event]:
    event = threading.Event()
    yield event
    event.set()


@pytest.fixture(autouse=True)
def _short_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_bench_in_time, "PICK_IN_TIME", 0.2)
    monkeypatch.setattr(_bench_heir, "HEIR_SILENCE", 0.6)


def _bench(torrents: Torrents, prober: Callable[..., Media]) -> Bench:
    return Bench(torrents, prober=prober, meta_budget=_META)


class _Late(Torrents):
    """Верх ранжира отдаёт метаданные через ``meta`` с, а свой спрос снимает за ``status`` с."""

    def __init__(self, meta: float, status: float = 0.0) -> None:
        super().__init__()
        self.meta, self.slow = meta, status

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float | ContactWait = 0.0
    ) -> list[TorrFile]:
        if torrent_hash == f"hash-{_POOL[0].magnet}":
            time.sleep(self.meta)
        return super().wait_files(torrent_hash, timeout, grace)

    def status(self, torrent_hash: str) -> dict[str, JsonValue]:
        if torrent_hash == f"hash-{_POOL[0].magnet}":
            time.sleep(self.slow)
        return super().status(torrent_hash)


def _slow_top(read: Callable[..., Media]) -> Callable[..., Media]:
    """ffprobe верха читает 1.5 с: ответ его пока не готов, а тяжёлый №2 уже прочитан."""

    def slow(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{_POOL[0].magnet}/" in source_url:
            time.sleep(1.5)
        return read(source_url, timeout=timeout, alive=alive)

    return slow


@pytest.mark.machine
def test_a_heavy_next_release_takes_over_from_a_top_silent_without_metadata(
    released: threading.Event,
) -> None:
    """🔴 «Оно» 30-09: №6 молчал без метаданных 20 с, готовый тяжёлый №33 сыграл всё равно.

    Очередь, осудив безмолвного, взяла бы ровно следующего, - наследник берётся сразу и
    без пометки срока: проверку честности он проходит так же, как прошёл бы в очереди.
    """
    bench = _bench(_Mute(released), probes(_POOL, _RUS, _HEAVY, _HEAVY))
    began = time.monotonic()

    prep = bench.resolve(plan(_POOL, recode_at=10.0), _ASKED, Said())

    assert prep.number == 2
    assert not prep.hurried
    assert time.monotonic() - began < _META - 1.0


@pytest.mark.machine
def test_a_heavy_next_release_waits_for_a_top_that_has_metadata_and_reads_long() -> None:
    """Метаданные у старшей есть, ffprobe читает долго: ответ близок, тяжёлый ждёт очереди."""
    slow = _slow_top(probes(_POOL, _RUS, _HEAVY, _HEAVY))

    prep = _bench(Torrents(), slow).resolve(plan(_POOL, recode_at=10.0), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_heavy_next_release_waits_for_a_top_whose_metadata_came_after_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Метаданные верха пришли позже срока подмены, но раньше порога молчания: он живой.

    Живые раздачи на стенде отдают метаданные за 0.3-8.1 с, и та, что ответила через 1 с при
    сроке 0.2, наследника не порождает - иначе зритель получит тяжёлую копию с перекодом.
    Окна по обе стороны секунды широкие: первая проверка после срока идёт на 0.4 с, порог 2 с.
    """
    monkeypatch.setattr(_bench_heir, "HEIR_SILENCE", 2.0)
    read = _slow_top(probes(_POOL, _RUS, _HEAVY, _HEAVY))

    prep = _bench(_Late(meta=1.0), read).resolve(plan(_POOL, recode_at=10.0), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_top_with_files_is_not_silent_while_its_supply_sample_hangs() -> None:
    """Список файлов пришёл сразу, а снятие спроса у TorrServer висит 1.5 с: верх не молчит.

    Отметка :attr:`_Prep.meta` встаёт только после этого запроса, и по ней верх выглядел бы
    безмолвным дольше порога, хотя метаданные у него давно есть.
    """
    read = probes(_POOL, _RUS, _HEAVY, _HEAVY)
    torrents = _Late(meta=0.0, status=1.5)

    prep = _bench(torrents, read).resolve(plan(_POOL, recode_at=10.0), _ASKED, Said())

    assert prep.number == 1


@pytest.mark.machine
def test_a_heavy_release_that_is_not_next_in_the_queue_does_not_inherit(
    released: threading.Event,
) -> None:
    """Наследник - только следующий: №2 без русского звука, тяжёлый №3 ждёт, пока его спросят."""
    bench = _bench(_Mute(released), probes(_POOL, _RUS, _ENG, _HEAVY))
    began = time.monotonic()

    prep = bench.resolve(plan(_POOL, recode_at=10.0), _ASKED, Said())

    assert prep.number == 3
    assert time.monotonic() - began >= _META - 0.5
