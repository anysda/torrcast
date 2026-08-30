"""Проверяет ожидание метаданных TorrServer через фейковые часы."""

import pytest

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.swarm_error import SwarmError


class _Recording(TorrServer):
    def __init__(self) -> None:
        super().__init__("http://torrserver")
        self.body: dict[str, object] = {}

    def _post(self, path: str, body: dict[str, object], json_body: bool = True) -> dict[str, str]:
        self.body = body
        return {"hash": "abc"}


def test_an_added_torrent_is_saved_so_its_disk_cache_survives_a_restart() -> None:
    server = _Recording()

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"

    assert server.body["save_to_db"] is True


class _Ready(TorrServer):
    def __init__(self, clock: FakeClock) -> None:
        super().__init__("http://torrserver", clock=clock)
        self.calls = 0

    def status(self, torrent_hash: str) -> dict[str, object]:
        self.calls += 1
        if self.calls < 3:
            return {}
        return {"file_stats": [{"id": 2, "path": "film.mkv", "length": 10}]}


def test_ожидание_метаданных_берёт_время_из_порта() -> None:
    clock = FakeClock()
    files = _Ready(clock).wait_files("hash", timeout=1.0)
    assert files[0].name == "film.mkv"
    assert clock.sleeps == [0.05, 0.07500000000000001]


#: Раздача, про рой которой служба говорит прямо: адреса есть, поговорить не удалось.
_EMPTY: dict[str, object] = {"total_peers": 8, "half_open_peers": 8, "active_peers": 0}
_ALIVE: dict[str, object] = {"total_peers": 8, "active_peers": 3, "connected_seeders": 2}


class _Warmed(TorrServer):
    """Прогрев, до которого очередь дошла на 40-й секунде: рой всё это время спрашивали."""

    def __init__(self, clock: FakeClock, wait: ContactWait, alive_until: float = 0.0) -> None:
        super().__init__("http://torrserver", clock=clock)
        self.fake = clock
        self.wait = wait
        self.alive_until = alive_until

    def status(self, torrent_hash: str) -> dict[str, object]:
        if self.fake.now >= 40.0:
            self.wait.activate(6.0)
        return dict(_ALIVE if self.fake.now < self.alive_until else _EMPTY)


def test_the_grace_counts_the_waiting_the_warm_up_has_already_stood() -> None:
    """Прогрев спрашивал рой с добавления раздачи: второй раз отсрочку он не платит."""
    clock = FakeClock()
    wait = ContactWait(6.0, clock)

    with pytest.raises(SwarmError):
        _Warmed(clock, wait).wait_files("hash", timeout=20.0, grace=wait)

    assert clock.now < 41.0, "рой пуст с первой секунды - приговор готов к вопросу"


def test_a_swarm_that_had_a_contact_gets_the_whole_grace_from_the_moment_it_went_quiet() -> None:
    """Контакт был - отсрочка идёт заново: иначе живая раздача выпала бы из каталога."""
    clock = FakeClock()
    wait = ContactWait(6.0, clock)

    with pytest.raises(SwarmError):
        _Warmed(clock, wait, alive_until=41.0).wait_files("hash", timeout=60.0, grace=wait)

    assert clock.now >= 47.0, "рой замолчал на 41-й секунде - отсрочка отсчитана от неё"


class _Mute(_Warmed):
    """Рой жив, а метаданные не едут: бюджет тут кончается сроком, а не отсрочкой."""

    def status(self, torrent_hash: str) -> dict[str, object]:
        if self.fake.now >= 40.0:
            self.wait.activate(6.0)
        return dict(_ALIVE)


def test_the_metadata_budget_counts_the_warm_up_too() -> None:
    """Двадцать секунд DHT прогрев уже отстоял: вопрос застаёт готовый ответ."""
    clock = FakeClock()
    wait = ContactWait(6.0, clock)

    with pytest.raises(SwarmError, match="gave no metadata"):
        _Mute(clock, wait).wait_files("hash", timeout=20.0, grace=wait)

    assert clock.now < 41.0, "бюджет метаданных отсчитан от добавления раздачи"
