"""Проверяет, что сроки подъёма службы оставляют место для обязательных щупов."""

from torrcast.adapters.torrserver.echoed import PROBE_TIMEOUT
from torrcast.adapters.torrserver.engine_limits import ADD_TIMEOUT, COMEBACK, SPARING, STEP, UP


def test_restart_deadlines_leave_room_for_a_probe_and_service_recovery() -> None:
    assert 0 < STEP < PROBE_TIMEOUT < SPARING
    assert ADD_TIMEOUT <= COMEBACK <= UP
