"""Щупы перед KILL укладываются в общий срок при любом числе раздач, отказ обрывает их."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from hass.starting import YIELD_SECONDS
from tests.fakes.clock import FakeClock
from tests.fakes.engine_service import Asked, FakeService, engine
from torrcast.adapters.torrserver.echoed import PROBE_TIMEOUT
from torrcast.adapters.torrserver.engine_restart import ADD_TIMEOUT, SPARING
from torrcast.adapters.torrserver.reading import Stop, reading
from torrcast.domain.server_down_error import ServerDownError
from torrcast.ports.abandon import slot as abandon_slot

LOCAL = "http://127.0.0.1:8090"
HUNG = requests.ReadTimeout("read timed out")


class SlowService:
    """Служба на зависе ``add``: жива, но каждый её ответ идёт полный срок щупа."""

    def __init__(self, clock: FakeClock, torrents: int, read: str | None = None) -> None:
        self._clock = clock
        self._hashes = [f"h{i}" for i in range(torrents)]
        self._read = read
        self.cached: list[str] = []

    def alive(self) -> bool:
        self._clock.now += PROBE_TIMEOUT
        return True

    def reading(self, stop: Stop) -> bool | None:
        return reading(self._post, stop)

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        self._clock.now += PROBE_TIMEOUT
        if path == "/torrents":
            return [{"hash": item, "stat": 3} for item in self._hashes]
        self.cached.append(body["hash"])
        return {"Readers": [{}, {}] if body["hash"] == self._read else []}


@pytest.mark.parametrize("torrents", [10, 50])
def test_probes_of_many_slow_torrents_end_within_the_budget(torrents: int) -> None:
    clock = FakeClock()
    service = FakeService()
    restart, _ = engine(service, clock)
    asked = Asked(HUNG)

    answer = restart.answered(LOCAL, SlowService(clock, torrents), asked, 30.0, add=True)

    assert answer == "answer"
    assert clock.now <= SPARING < YIELD_SECONDS, f"решение через {clock.now} с"
    assert service.restarted == 0, "не досказала, читают ли: «не знаю», службу щадим"
    assert asked.timeouts == [ADD_TIMEOUT, 30.0 - ADD_TIMEOUT]


@pytest.mark.parametrize("read", ["h0", "h9"], ids=["read-first", "read-past-the-budget"])
def test_a_running_show_beside_many_torrents_is_still_spared(read: str) -> None:
    clock = FakeClock()
    service = FakeService()
    restart, _ = engine(service, clock)
    probes = SlowService(clock, 10, read)

    assert restart.answered(LOCAL, probes, Asked(HUNG), 30.0, add=True) == "answer"
    assert service.restarted == 0, "живой показ не рвётся ради одного медленного add"
    assert probes.cached[0] == "h0"


def test_calling_the_start_off_during_the_probes_answers_after_one_probe() -> None:
    clock = FakeClock()
    service = FakeService()
    restart, _ = engine(service, clock)
    called_off = PROBE_TIMEOUT + 1.0  # человек сказал «не жду», пока шёл ``list``
    abandon_slot.install(lambda: clock.now >= called_off)
    asked = Asked(HUNG)

    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, SlowService(clock, 10), asked, 30.0, add=True)
    assert clock.now - called_off <= PROBE_TIMEOUT, f"ответ через {clock.now - called_off} с"
    assert service.restarted == 0
    assert asked.timeouts == [ADD_TIMEOUT]
