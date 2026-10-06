"""Повисшая или упавшая служба раздач поднимается сама, и вопрос повторяется один раз."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
import requests

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver import torr_server
from torrcast.adapters.torrserver.engine_restart import ADD_TIMEOUT, COMEBACK, EngineRestart
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.server_down_error import ServerDownError

LOCAL = "http://127.0.0.1:8090"


class _Service:
    """Менеджер служб: знает ли службу, поднимает ли её сам, и сколько раз её подняли мы."""

    def __init__(self, known: bool = True, coming: bool = False, restarts: bool = True) -> None:
        self._known = known
        self._coming = coming
        self._restarts = restarts
        self.restarted = 0

    def known(self) -> bool:
        return self._known

    def coming(self) -> bool:
        return self._coming

    def restart(self) -> bool:
        self.restarted += 1
        return self._restarts


def _down(cause: Exception) -> ServerDownError:
    try:
        raise ServerDownError("TorrServer does not answer") from cause
    except ServerDownError as exc:
        return exc


def _asked(*fails: Exception) -> Callable[[], str]:
    """Вопрос, который падает по очереди на ``fails``, а потом отвечает."""
    left = list(fails)

    def ask() -> str:
        if left:
            raise _down(left.pop(0))
        return "answer"

    return ask


def _engine(service: _Service, clock: FakeClock) -> tuple[EngineRestart, list[float]]:
    """Подъём и список моментов, когда он сказал экрану о перезапуске."""
    engine = EngineRestart(service, clock)  # type: ignore[arg-type]
    told: list[float] = []
    engine.tell = lambda: told.append(clock.now)
    return engine, told


def test_a_hung_service_is_restarted_and_the_question_asked_again() -> None:
    service = _Service()
    engine, told = _engine(service, FakeClock())

    answer = engine.answered(LOCAL, lambda: True, _asked(requests.ReadTimeout("read timed out")))

    assert answer == "answer"
    assert service.restarted == 1
    assert len(told) == 1


def test_a_crashed_service_is_left_to_systemd_when_it_comes_back_by_itself() -> None:
    clock = FakeClock()
    service = _Service(coming=True)
    engine, _ = _engine(service, clock)

    answer = engine.answered(
        LOCAL, lambda: clock.now >= 5.0, _asked(requests.ConnectionError("refused"))
    )

    assert answer == "answer"
    assert service.restarted == 0


def test_a_crashed_service_nobody_brings_back_is_restarted() -> None:
    clock = FakeClock()
    service = _Service(coming=True)
    engine, _ = _engine(service, clock)
    began = clock.now

    answer = engine.answered(
        LOCAL, lambda: service.restarted > 0, _asked(requests.ConnectionError("refused"))
    )

    assert answer == "answer"
    assert service.restarted == 1
    assert clock.now - began >= COMEBACK


@pytest.mark.parametrize(
    ("url", "service", "restarted"),
    [
        ("http://torrserver.example:8090", _Service(), 0),
        (LOCAL, _Service(known=False), 0),
        (LOCAL, _Service(restarts=False), 1),
    ],
    ids=["foreign", "no-service", "restart-refused"],
)
def test_what_we_cannot_restart_keeps_the_old_refusal(
    url: str, service: _Service, restarted: int
) -> None:
    engine, _ = _engine(service, FakeClock())

    with pytest.raises(ServerDownError):
        engine.answered(url, lambda: True, _asked(requests.ReadTimeout("read timed out")))
    assert service.restarted == restarted


def test_a_service_that_answered_badly_is_not_restarted() -> None:
    service = _Service()
    engine, _ = _engine(service, FakeClock())

    with pytest.raises(ServerDownError):
        engine.answered(LOCAL, lambda: True, _asked(requests.HTTPError("500")))
    assert service.restarted == 0


def test_parallel_questions_on_one_hang_restart_the_service_once() -> None:
    service = _Service()
    engine, told = _engine(service, FakeClock())
    first = _asked(requests.ReadTimeout("read timed out"))

    def second() -> str:
        # Пока этот вопрос ждал ответа, соседний упал на том же зависе и поднял службу.
        engine.answered(LOCAL, lambda: True, first)
        raise _down(requests.ReadTimeout("read timed out"))

    answers: Iterator[Callable[[], str]] = iter([second, lambda: "answer"])
    answer = engine.answered(LOCAL, lambda: True, lambda: next(answers)())

    assert answer == "answer"
    assert service.restarted == 1
    assert len(told) == 1


class _HungOnce:
    """Сессия службы, у которой первый ``add`` не дождался ответа, а второй пришёл."""

    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def post(self, _url: str, json: dict[str, object], timeout: float) -> object:
        self.timeouts.append(timeout)
        if len(self.timeouts) == 1:
            raise requests.ReadTimeout("read timed out")
        return _Answer({"hash": "abc", "data": "known"})


class _Answer:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_an_add_that_hung_on_the_service_restarts_it_and_gets_the_torrent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _Service()
    engine, told = _engine(service, FakeClock())
    monkeypatch.setattr(torr_server, "ENGINE", engine)
    server = TorrServer(LOCAL)
    session = _HungOnce()
    server._session = session  # type: ignore[assignment]
    monkeypatch.setattr(server, "alive", lambda: True)

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"
    assert service.restarted == 1
    assert len(told) == 1
    assert session.timeouts == [ADD_TIMEOUT, ADD_TIMEOUT]
    assert server.timeout > ADD_TIMEOUT
