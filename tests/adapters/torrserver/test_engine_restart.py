"""Повисшая или упавшая служба раздач поднимается сама, и вопрос повторяется один раз."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
import requests

from tests.fakes.clock import FakeClock
from tests.fakes.engine_service import Asked, FakeProbes, FakeService, down, engine
from torrcast.adapters.torrserver import torr_server
from torrcast.adapters.torrserver.echoed import PROBE_TIMEOUT
from torrcast.adapters.torrserver.engine_restart import ADD_TIMEOUT, COMEBACK
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.server_down_error import ServerDownError

LOCAL = "http://127.0.0.1:8090"
HUNG = requests.ReadTimeout("read timed out")
REFUSED = requests.ConnectionError("refused")


def test_a_hung_service_is_restarted_and_the_question_asked_again() -> None:
    service = FakeService()
    restart, told = engine(service, FakeClock())

    answer = restart.answered(LOCAL, FakeProbes(), Asked(HUNG), 30.0, add=True)

    assert answer == "answer"
    assert service.restarted == 1
    assert len(told) == 1


def test_a_crashed_service_is_left_to_systemd_when_it_comes_back_by_itself() -> None:
    clock = FakeClock()
    service = FakeService(state="activating")
    restart, _ = engine(service, clock)

    probes = FakeProbes(alive=lambda: clock.now >= 5.0)
    answer = restart.answered(LOCAL, probes, Asked(REFUSED), 30.0, add=False)

    assert answer == "answer"
    assert service.restarted == 0


def test_a_get_after_a_crash_restores_the_torrent_before_repeating_get() -> None:
    """Упавшая служба теряет память: повторный get без add честно дал бы 404."""
    clock = FakeClock()
    service = FakeService(state="activating")
    restart, _ = engine(service, clock)
    calls: list[str] = []

    def get(_timeout: float) -> str:
        calls.append("get")
        if len(calls) == 1:
            raise down(REFUSED)
        return "files"

    answer = restart.answered(
        LOCAL,
        FakeProbes(alive=lambda: clock.now >= 5.0),
        get,
        30.0,
        add=False,
        recover=lambda: calls.append("add"),
    )

    assert answer == "files"
    assert calls == ["get", "add", "get"]


def test_torrserver_readds_its_known_magnet_before_retrying_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """После systemd-подъёма у службы пустая память, так что одного ``get`` недостаточно."""
    key = "0123456789abcdef0123456789abcdef01234567"
    magnet = f"magnet:?xt=urn:btih:{key}"
    calls: list[str] = []

    class _Restarted:
        def answered(
            self,
            _base: str,
            _probes: object,
            ask: Callable[[float], object],
            timeout: float,
            add: bool,
            recover: Callable[[], object],
        ) -> object:
            if not add:
                recover()
            return ask(timeout)

    server = TorrServer(LOCAL)

    def ask(_path: str, body: dict[str, object], _json: bool, _timeout: float) -> object:
        calls.append(str(body["action"]))
        return {"hash": key, "data": "known"} if body["action"] == "add" else {"file_stats": []}

    monkeypatch.setattr(torr_server, "ENGINE", _Restarted())
    monkeypatch.setattr(server, "_ask", ask)
    assert server.add(magnet) == key
    calls.clear()

    assert server.status(key) == {"file_stats": []}
    assert calls == ["add", "get"]


def test_a_crashed_service_nobody_brings_back_is_restarted() -> None:
    clock = FakeClock()
    service = FakeService(state="activating")
    restart, told = engine(service, clock)

    probes = FakeProbes(alive=lambda: service.restarted > 0)
    answer = restart.answered(LOCAL, probes, Asked(REFUSED), 30.0, add=False)

    assert answer == "answer"
    assert service.restarted == 1
    assert clock.now >= COMEBACK
    assert len(told) == 1, "экрану о подъёме говорят один раз"


def test_a_service_systemd_gave_up_on_is_restarted_at_once() -> None:
    clock = FakeClock()
    service = FakeService(state="failed")
    restart, _ = engine(service, clock)

    probes = FakeProbes(alive=lambda: service.restarted > 0)
    answer = restart.answered(LOCAL, probes, Asked(REFUSED), 30.0, add=False)

    assert answer == "answer"
    assert service.restarted == 1
    assert clock.now < COMEBACK


def test_a_service_someone_stopped_is_refused_at_once() -> None:
    clock = FakeClock()
    service = FakeService(state="inactive")
    restart, told = engine(service, clock)

    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(lambda: False), Asked(REFUSED), 30.0, add=False)
    assert service.restarted == 0
    assert clock.now == 0.0, "остановленную человеком службу ждать нечего"
    assert told == []


def test_a_service_being_stopped_is_waited_for_and_left_alone() -> None:
    clock = FakeClock()
    service = FakeService(state="deactivating")
    restart, _ = engine(service, clock)

    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(lambda: False), Asked(REFUSED), 30.0, add=False)
    assert service.restarted == 0
    assert clock.now >= COMEBACK


def test_a_service_restarted_by_hand_is_waited_for() -> None:
    clock = FakeClock()
    service = FakeService(state="deactivating")
    restart, _ = engine(service, clock)

    probes = FakeProbes(alive=lambda: clock.now >= 3.0)
    answer = restart.answered(LOCAL, probes, Asked(REFUSED), 30.0, add=False)

    assert answer == "answer"
    assert service.restarted == 0


@pytest.mark.parametrize(
    ("url", "service", "restarted"),
    [
        ("http://torrserver.example:8090", FakeService(), 0),
        (LOCAL, FakeService(restarts=False), 1),
    ],
    ids=["foreign", "restart-refused"],
)
def test_what_we_cannot_restart_keeps_the_old_refusal(
    url: str, service: FakeService, restarted: int
) -> None:
    restart, _ = engine(service, FakeClock())

    with pytest.raises(ServerDownError):
        restart.answered(url, FakeProbes(), Asked(HUNG, HUNG), 30.0, add=False)
    assert service.restarted == restarted


def test_a_service_that_answered_badly_is_not_restarted() -> None:
    service = FakeService()
    restart, _ = engine(service, FakeClock())

    with pytest.raises(ServerDownError):
        restart.answered(LOCAL, FakeProbes(), Asked(requests.HTTPError("500")), 30.0, add=False)
    assert service.restarted == 0


def test_parallel_questions_on_one_hang_restart_the_service_once() -> None:
    service = FakeService()
    restart, told = engine(service, FakeClock())
    first = Asked(HUNG)

    def second(_timeout: float) -> str:
        # Пока этот вопрос ждал ответа, соседний упал на том же зависе и поднял службу.
        restart.answered(LOCAL, FakeProbes(), first, 30.0, add=True)
        raise down(HUNG)

    answers: Iterator[Callable[[float], str]] = iter([second, lambda _t: "answer"])
    answer = restart.answered(LOCAL, FakeProbes(), lambda t: next(answers)(t), 30.0, add=True)

    assert answer == "answer"
    assert service.restarted == 1
    assert len(told) == 1


class _HungOnce:
    """Сессия службы, у которой первый ``add`` не дождался ответа, а второй пришёл."""

    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def post(self, _url: str, json: dict[str, object], timeout: float) -> object:
        self.timeouts.append(timeout)
        if json.get("action") == "list":
            return _Answer([])
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
    service = FakeService()
    restart, told = engine(service, FakeClock())
    monkeypatch.setattr(torr_server, "ENGINE", restart)
    server = TorrServer(LOCAL)
    session = _HungOnce()
    server._session = session  # type: ignore[assignment]
    monkeypatch.setattr(server, "alive", lambda: True)

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"
    assert service.restarted == 1
    assert len(told) == 1
    assert session.timeouts == [ADD_TIMEOUT, PROBE_TIMEOUT, ADD_TIMEOUT]
    assert server.timeout > ADD_TIMEOUT
