"""Проверяет ожидание метаданных TorrServer через фейковые часы."""

import pytest

from torrcast.adapters.torrserver import torr_server
from torrcast.adapters.torrserver.torr_server import TorrServer


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
