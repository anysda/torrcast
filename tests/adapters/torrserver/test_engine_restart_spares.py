"""Когда службу раздач убивать нельзя: вопрос ждёт прежний срок и отдаёт прежний отказ."""

from __future__ import annotations

import pytest
import requests

from tests.fakes.clock import FakeClock
from tests.fakes.engine_service import Asked, FakeProbes, FakeService, engine
from torrcast.adapters.torrserver.engine_restart import ADD_TIMEOUT, PAUSE, UP
from torrcast.adapters.torrserver.reading import Stop
from torrcast.domain.server_down_error import ServerDownError
from torrcast.ports.abandon import slot as abandon_slot

LOCAL = "http://127.0.0.1:8090"
HUNG = requests.ReadTimeout("read timed out")


@pytest.mark.parametrize("reading", [True, None], ids=["show-running", "cannot-tell"])
def test_a_slow_add_beside_a_running_show_waits_the_old_term(reading: bool | None) -> None:
    service = FakeService()
    restart, told = engine(service, FakeClock())
    asked = Asked(HUNG)

    answer = restart.answered(LOCAL, FakeProbes(reading=reading), asked, 30.0, add=True)

    assert answer == "answer"
    assert service.restarted == 0, "живой показ не рвётся ради одного медленного add"
    assert asked.timeouts == [ADD_TIMEOUT, 30.0 - ADD_TIMEOUT]
    assert told == []


def test_a_service_whose_echo_is_dead_too_is_restarted_without_asking_readers() -> None:
    service = FakeService()
    restart, _ = engine(service, FakeClock())
    probes = FakeProbes(alive=lambda: service.restarted > 0, reading=True)

    assert restart.answered(LOCAL, probes, Asked(HUNG), 30.0, add=True) == "answer"
    assert service.restarted == 1
    assert probes.asked_reading == 0


def test_a_hang_the_restart_did_not_cure_is_not_restarted_again_within_the_pause() -> None:
    clock = FakeClock()
    service = FakeService()
    restart, _ = engine(service, clock)

    with pytest.raises(ServerDownError):  # подъём не помог: повтор тоже повис
        restart.answered(LOCAL, FakeProbes(), Asked(HUNG, HUNG), 30.0, add=True)
    clock.now += PAUSE / 2
    later = Asked(HUNG, HUNG)
    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(), later, 30.0, add=True)

    assert service.restarted == 1
    assert later.timeouts == [ADD_TIMEOUT, 30.0 - ADD_TIMEOUT], "прежний срок и прежний отказ"
    clock.now += PAUSE
    restart.answered(LOCAL, FakeProbes(), Asked(HUNG), 30.0, add=True)
    assert service.restarted == 2


def test_a_crashed_service_systemd_gave_up_on_is_not_restarted_within_the_pause() -> None:
    clock = FakeClock()
    service = FakeService()
    restart, _ = engine(service, clock)
    restart.answered(LOCAL, FakeProbes(), Asked(HUNG), 30.0, add=True)
    service.current = "failed"

    refused = requests.ConnectionError("refused")
    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(lambda: False), Asked(refused), 30.0, add=False)
    assert service.restarted == 1


def test_a_foreign_service_add_gets_the_whole_old_term_at_once() -> None:
    service = FakeService()
    restart, _ = engine(service, FakeClock())
    asked = Asked(HUNG)

    with pytest.raises(ServerDownError):
        restart.answered("http://torrserver.example:8090", FakeProbes(), asked, 30.0, add=True)
    assert asked.timeouts == [30.0]
    assert service.restarted == 0


def test_a_local_add_without_a_service_waits_the_rest_of_the_old_term() -> None:
    service = FakeService(known=False)
    restart, _ = engine(service, FakeClock())
    asked = Asked(HUNG)

    assert restart.answered(LOCAL, FakeProbes(), asked, 30.0, add=True) == "answer"
    assert asked.timeouts == [ADD_TIMEOUT, 30.0 - ADD_TIMEOUT]
    assert service.restarted == 0


def test_a_short_question_that_timed_out_does_not_restart_the_service() -> None:
    service = FakeService()
    restart, _ = engine(service, FakeClock())
    asked = Asked(HUNG)

    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(), asked, 3.0, add=False)
    assert asked.timeouts == [3.0]
    assert service.restarted == 0


def test_a_start_the_person_called_off_does_not_restart_the_service() -> None:
    service = FakeService()
    restart, _ = engine(service, FakeClock())
    abandon_slot.install(lambda: True)
    asked = Asked(HUNG)

    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(), asked, 30.0, add=True)
    assert asked.timeouts == [ADD_TIMEOUT]
    assert service.restarted == 0


def test_calling_the_start_off_ends_the_wait_for_the_restarted_service() -> None:
    clock = FakeClock()
    service = FakeService()
    restart, _ = engine(service, clock)
    abandon_slot.install(lambda: service.restarted > 0 and clock.now >= 1.0)
    asked = Asked(HUNG)

    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(lambda: False), asked, 30.0, add=True)
    assert service.restarted == 1
    assert clock.now < UP / 2, "новое «Играть» не ждёт подъёма ради брошенного показа"
    assert asked.timeouts == [ADD_TIMEOUT]


def test_the_pause_holds_across_processes_of_the_product() -> None:
    clock = FakeClock()
    service = FakeService()
    bridge, _ = engine(service, clock)
    bridge.answered(LOCAL, FakeProbes(), Asked(HUNG), 30.0, add=True)
    clock.now += PAUSE / 2
    show, _ = engine(service, clock)  # новый показ - новый процесс, своя память пуста

    with pytest.raises(ServerDownError):
        show.answered(LOCAL, FakeProbes(), Asked(HUNG, HUNG), 30.0, add=True)
    assert service.restarted == 1


def test_a_kill_by_another_process_during_the_probes_is_not_repeated() -> None:
    clock = FakeClock()
    service = FakeService()
    bridge, _ = engine(service, clock)
    show, _ = engine(service, clock)

    def readers_while_the_bridge_kills(stop: Stop) -> bool:
        # Пока показ спрашивал читателей, мост упал на том же зависе и убил службу.
        bridge.answered(LOCAL, FakeProbes(), Asked(HUNG), 30.0, add=True)
        return False

    probes = FakeProbes(reading=None)
    probes.reading = readers_while_the_bridge_kills  # type: ignore[method-assign]
    with pytest.raises(ServerDownError):
        show.answered(LOCAL, probes, Asked(HUNG, HUNG), 30.0, add=True)
    assert service.restarted == 1
