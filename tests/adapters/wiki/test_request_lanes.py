"""Проверяет приоритет клика над ещё не начавшимся фоном Wikimedia."""

import threading
import time

import pytest

from torrcast.adapters.wiki import http_json_client
from torrcast.adapters.wiki.request_lanes import RequestLanes


@pytest.mark.machine
def test_a_card_gets_the_next_lane_before_a_waiting_background_wave() -> None:
    """Завершившийся фон выпускает первым клик, а не следующий пакет прогрева."""
    lanes = RequestLanes()
    assert all(lanes.acquire(0.1, foreground=False) for _ in range(5))
    started = threading.Event()
    card_started = threading.Event()
    finished: list[str] = []

    def background() -> None:
        started.set()
        assert lanes.acquire(1.0, foreground=False)
        finished.append("background")
        lanes.release()

    def card() -> None:
        card_started.set()
        assert lanes.acquire(1.0, foreground=True)
        finished.append("card")
        lanes.release()

    behind = threading.Thread(target=background)
    behind.start()
    assert started.wait(1.0)
    time.sleep(0.02)
    urgent = threading.Thread(target=card)
    urgent.start()
    assert card_started.wait(1.0)
    time.sleep(0.02)
    lanes.release()
    urgent.join(1.0)
    behind.join(1.0)
    for _ in range(4):
        lanes.release()
    assert finished == ["card", "background"]


@pytest.mark.machine
def test_a_busy_sparql_host_does_not_hold_back_wikipedia(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пять долгих запросов к одному хосту не отнимают полосу у другого хоста."""
    held = threading.Event()
    entered: list[str] = []

    class _Reply:
        status = 200

        def read(self) -> bytes:
            return b"{}"

    class _Connection:
        def __init__(self, host: str, **_kwargs: object) -> None:
            self.host = host

        def request(self, *_args: object, **_kwargs: object) -> None:
            entered.append(self.host)
            if self.host == "query.wikidata.org":
                held.wait(2.0)

        def getresponse(self) -> _Reply:
            return _Reply()

        def close(self) -> None:
            return None

    monkeypatch.setattr(http_json_client, "_IPv4Connection", _Connection)
    client = http_json_client.HttpJsonClient("torrcast/test")
    shelf = [
        threading.Thread(target=client.get, args=("query.wikidata.org", "/sparql", {}, {}, 2.0))
        for _ in range(5)
    ]
    for thread in shelf:
        thread.start()
    while entered.count("query.wikidata.org") < 5:
        time.sleep(0.01)
    try:
        assert client.get("ru.wikipedia.org", "/w/api.php", {}, {}, 0.2, foreground=True) == {}
    finally:
        held.set()
        for thread in shelf:
            thread.join(2.0)
