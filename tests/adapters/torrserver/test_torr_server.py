"""Проверяет ожидание метаданных TorrServer через фейковые часы."""

import pytest

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver import torr_server
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.swarm_error import SwarmError


class _Response:
    def __init__(self, payload: object = None) -> None:
        self.payload = payload
        self.closed = False

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def post(self, *_args: object, **_kwargs: object) -> _Response:
        return self.response

    def get(self, *_args: object, **_kwargs: object) -> _Response:
        return self.response


def test_a_torrserver_response_is_closed_after_a_command() -> None:
    response = _Response({"hash": "abc"})
    server = TorrServer("http://torrserver")
    server._session = _Session(response)  # type: ignore[assignment]

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"
    assert response.closed


def test_a_torrserver_probe_closes_its_response() -> None:
    response = _Response()
    server = TorrServer("http://torrserver")
    server._session = _Session(response)  # type: ignore[assignment]

    assert server.alive()
    assert response.closed


class _Recording(TorrServer):
    """Служба, у которой в базе уже лежат раздачи ``known``: их ``add`` отвечает с ``data``."""

    def __init__(self, known: tuple[str, ...] = ()) -> None:
        super().__init__("http://torrserver")
        self.known = known
        self.body: dict[str, object] = {}
        self.saves: list[object] = []

    def _post(self, path: str, body: dict[str, object], json_body: bool = True) -> dict[str, str]:
        self.body = body
        if body["action"] == "add":
            self.saves.append(body["save_to_db"])
        return {"hash": "abc", "data": '{"TorrServer":{}}' if "abc" in self.known else ""}


def test_an_added_torrent_is_saved_so_its_disk_cache_survives_a_restart() -> None:
    server = _Recording()

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"

    assert server.saves[-1] is True


def test_a_torrent_already_in_the_service_base_is_not_written_again() -> None:
    """Запись в базу переписывает её целиком под общим замком: ``add`` показа ждал 2.5 с."""
    server = _Recording(known=("abc",))

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"

    assert server.saves == [False]


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


def test_a_parked_release_is_closed_and_its_disk_cache_kept() -> None:
    """``rem`` стирал кэш раздачи на диске: закладка тянула свой кусок из роя заново."""
    server = _Recording()

    assert server.park("abc") is True
    assert server.body == {"action": "drop", "hash": "abc"}

    assert server.drop("abc") is True
    assert server.body == {"action": "rem", "hash": "abc"}, "снос остаётся сносом"


def test_a_closed_torrent_is_forgotten_before_a_restart_can_restore_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forgotten: list[str] = []

    class _Recovery:
        def forget(self, torrent_hash: str) -> None:
            forgotten.append(torrent_hash)

    monkeypatch.setattr(torr_server, "RECOVERY", _Recovery())
    server = _Recording()

    assert server.drop("abc") is True
    assert forgotten == ["abc"]


class _Listing(TorrServer):
    def __init__(self, payload: object) -> None:
        super().__init__("http://torrserver")
        self.payload = payload

    def _post(self, path: str, body: dict[str, object], json_body: bool = True) -> object:
        return self.payload


def test_the_base_lists_hashes_in_lower_case_whatever_the_service_answers() -> None:
    """Хэши из магнитов уборка сверяет в нижнем регистре: верхний не нашёлся бы никогда."""
    server = _Listing([{"hash": "ABCDEF" * 6 + "0123"}, {"hash": ""}, "мусор"])

    assert server.hashes() == {"abcdef" * 6 + "0123"}
    assert server.listed("abcdef" * 6 + "0123")
