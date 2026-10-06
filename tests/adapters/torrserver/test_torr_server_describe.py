"""Службу раздач и описатель связывают ``add`` и снятие раздачи."""

from collections.abc import Callable
from typing import Any

import pytest

from torrcast.adapters.torrserver.describer import DESCRIBER
from torrcast.adapters.torrserver.torr_server import TorrServer


class _Response:
    def __init__(self, payload: Any = None) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, payload: Any = None) -> None:
        self.payload = payload
        self.sent: list[object] = []

    def post(self, *_args: object, **kwargs: object) -> _Response:
        self.sent.append(kwargs.get("json"))
        return _Response(self.payload)


def test_an_added_torrent_is_handed_to_the_describer(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(DESCRIBER, "later", lambda base, key: asked.append((base, key)))
    server = TorrServer("http://torrserver/")
    server._session = _Session({"hash": "abc"})  # type: ignore[assignment]

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"
    assert asked == [("http://torrserver", "abc")]


@pytest.mark.parametrize(("method", "action"), [("drop", "rem"), ("park", "drop")])
def test_a_closed_torrent_is_off_limits_to_the_describer(
    method: str, action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    shut: list[str] = []

    def close(torrent_hash: str, remove: Callable[[], bool], idle: Callable[[], bool]) -> bool:
        shut.append(torrent_hash)
        assert idle() is True  # у службы читателей нет
        return remove()

    monkeypatch.setattr(DESCRIBER, "close", close)
    server = TorrServer("http://torrserver")
    session = _Session()
    server._session = session  # type: ignore[assignment]

    assert getattr(server, method)("abc") is True
    assert shut == ["abc"]
    assert session.sent == [{"action": "get", "hash": "abc"}, {"action": action, "hash": "abc"}]
