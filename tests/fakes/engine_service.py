"""Подделки для подъёма службы раздач: менеджер служб, щупы службы и вопрос к ней."""

from __future__ import annotations

from collections.abc import Callable

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.engine_restart import EngineRestart
from torrcast.domain.server_down_error import ServerDownError


class FakeService:
    """Менеджер служб: знает ли службу, в каком она состоянии и сколько раз её подняли мы."""

    def __init__(self, known: bool = True, state: str = "active", restarts: bool = True) -> None:
        self._known = known
        self.current = state
        self._restarts = restarts
        self.restarted = 0

    def known(self) -> bool:
        return self._known

    def state(self) -> str:
        return self.current

    def restart(self) -> bool:
        self.restarted += 1
        return self._restarts


class FakeProbes:
    """Щупы службы: отвечает ли ``/echo`` и читают ли раздачу; считает вопросы о чтении."""

    def __init__(
        self, alive: Callable[[], bool] = lambda: True, reading: bool | None = False
    ) -> None:
        self._alive = alive
        self._reading = reading
        self.asked_reading = 0

    def alive(self) -> bool:
        return self._alive()

    def reading(self) -> bool | None:
        self.asked_reading += 1
        return self._reading


def down(cause: Exception) -> ServerDownError:
    """Отказ клиента службы с причиной ``cause``, как его поднимает ``TorrServer._ask``."""
    try:
        raise ServerDownError("TorrServer does not answer") from cause
    except ServerDownError as exc:
        return exc


class Asked:
    """Вопрос, который падает по очереди на ``fails``, а потом отвечает; помнит сроки."""

    def __init__(self, *fails: Exception) -> None:
        self._left = list(fails)
        self.timeouts: list[float] = []

    def __call__(self, timeout: float) -> str:
        self.timeouts.append(timeout)
        if self._left:
            raise down(self._left.pop(0))
        return "answer"


def engine(service: FakeService, clock: FakeClock) -> tuple[EngineRestart, list[float]]:
    """Подъём и список моментов, когда он сказал экрану о перезапуске."""
    made = EngineRestart(service, clock)  # type: ignore[arg-type]
    told: list[float] = []
    made.tell = lambda: told.append(clock.now)
    return made, told


__all__ = ["Asked", "FakeProbes", "FakeService", "down", "engine"]
