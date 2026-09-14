"""Держимая раздача не закрывается TorrServer по тайм-ауту, пока её держат карточка или показ."""

from __future__ import annotations

import threading

from tests.usecases.select_bench.world import Torrents, probes, rel
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench_keep import KEEP_CEILING, _keep_open
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.torrent_claims import CLAIMS


class _Timed(Torrents):
    """Служба с тайм-аутом закрытия в настройках и счётчиком продлений по хэшу."""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self.timeout = timeout
        self.asked: list[str] = []

    def disconnect_timeout(self) -> float:
        return self.timeout

    def files(self, torrent_hash: str) -> list[TorrFile]:
        self.asked.append(torrent_hash)
        return self.known


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def test_a_held_torrent_is_asked_about_more_often_than_it_would_time_out() -> None:
    """Каждое продление приходит раньше, чем TorrServer успел бы закрыть раздачу."""
    engine, clock = _Timed(30.0), _Clock()

    asked = _keep_open(
        engine, "h", 30.0, lambda: clock.now < 95, lambda: KEEP_CEILING, clock, clock.wait
    )

    assert asked == 10 and set(engine.asked) == {"h"}
    assert clock.waits and max(clock.waits) < engine.timeout


def test_a_released_hold_stops_the_extension_at_once() -> None:
    """Держание снято - ни одного запроса больше: закрытие дальше решает TorrServer."""
    engine, clock = _Timed(30.0), _Clock()

    assert (
        _keep_open(engine, "h", 30.0, lambda: False, lambda: KEEP_CEILING, clock, clock.wait) == 0
    )
    assert engine.asked == []


def test_a_card_left_open_is_extended_no_longer_than_the_ceiling() -> None:
    """Брошенная открытой карточка держит раздачу не вечно, а до потолка."""
    engine, clock = _Timed(120.0), _Clock()

    asked = _keep_open(engine, "h", 120.0, lambda: True, lambda: KEEP_CEILING, clock, clock.wait)

    assert clock.now >= KEEP_CEILING and clock.now - clock.waits[-1] < KEEP_CEILING
    assert asked == KEEP_CEILING / 20  # дальше минуты get не продлевает: шаг 20 с
    assert engine.asked == ["h"] * asked


def test_a_silent_service_is_asked_again_next_step() -> None:
    """Промолчавшая служба не рвёт продление: следующий шаг спросит снова."""

    class _Silent(_Timed):
        def files(self, torrent_hash: str) -> list[TorrFile]:
            super().files(torrent_hash)
            raise ServerDownError("молчит")

    engine, clock = _Silent(30.0), _Clock()

    assert (
        _keep_open(engine, "h", 30.0, lambda: clock.now < 25, lambda: 60.0, clock, clock.wait) == 3
    )


def test_the_chosen_release_of_the_bench_is_kept_open_until_it_is_dropped() -> None:
    """Выбор стенда продлевается, пока раздача за стендом; уборка стенда продление гасит."""
    engine, clock = _Timed(30.0), _Clock()
    bench = Bench(engine, prober=probes([]), clock=clock)
    chosen = _Prep(number=1, release=rel(), torrent_hash="hash-держимый")
    bench.preps[("p", 1)] = chosen
    CLAIMS.claim(chosen.torrent_hash, bench)

    def step(seconds: float) -> None:
        clock.wait(seconds)
        if len(clock.waits) == 3:  # третий шаг: карточку закрыли, стенд убран
            bench.drop_all()

    bench.keep_wait = step
    bench.keep_only(chosen)
    _join("hash-держимый")

    assert engine.asked == ["hash-держимый"] * 3 and clock.waits == [10.0] * 3
    assert engine.dropped == ["hash-держимый"] and bench.keep_until == {}


def test_a_service_that_does_not_name_its_timeout_is_not_extended() -> None:
    """Подделке службы без настроек продлевать нечего: поток не заводится вовсе."""
    engine = Torrents()
    bench = Bench(engine, prober=probes([]))
    chosen = _Prep(number=1, release=rel(), torrent_hash="hash-без-настроек")
    bench.preps[("p", 1)] = chosen

    bench.keep_only(chosen)

    assert bench.keep_until == {}


def _join(torrent_hash: str) -> None:
    for thread in threading.enumerate():
        if thread.name == f"keep-{torrent_hash}":
            thread.join(5.0)
            assert not thread.is_alive()
