"""Проверяет устройство HTTPS-клиента Wikimedia без обращения в сеть."""

from __future__ import annotations

import http.server
import socket
import ssl
import threading
from typing import Any, ClassVar

import pytest

from tests.conftest import free_port
from torrcast.adapters.wiki import http_json_client
from torrcast.adapters.wiki.http_json_client import HttpJsonClient, _IPv4Connection


def test_keeps_user_agent() -> None:
    """Клиент хранит переданное имя автоматики для каждого запроса."""
    assert HttpJsonClient("torrcast/test").user_agent == "torrcast/test"


class _Store(http.server.BaseHTTPRequestHandler):
    """Склад картинок на одну пробу: отдаёт постер и помнит, кем назвался спросивший."""

    poster: ClassVar[bytes] = b""
    seen: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        _Store.seen.append(self.headers.get("User-Agent", ""))
        if self.path != "/poster.jpg":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(_Store.poster)))
        self.end_headers()
        self.wfile.write(_Store.poster)

    def log_message(self, fmt: str, *args: Any) -> None:
        return None


@pytest.mark.machine
def test_a_picture_is_fetched_over_real_tls_and_by_ipv4(
    tls: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Настоящая раздача, настоящий TLS: картинка приезжает байтами, а имя - своё.

    Постер тянет СЕРВ, а не карточка (:data:`hass.posters.ROUTE`), и тянет он его тем же
    клиентом, что и справку: та же память адресов, тот же проверенный TLS и тот же
    именной ``User-Agent`` - без него Wikimedia отвечает 429 уже на втором запросе подряд.
    Проверяется это на своей раздаче, а не на Wikimedia: чужой хост в прогоне мерил бы
    доступность Wikimedia, а не клиента.
    """
    _Store.poster = b"\xff\xd8\xff\xe0" + b"picture" * 100
    _Store.seen = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls[0], tls[1])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), _Store)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True, name="store").start()
    monkeypatch.setattr(_IPv4Connection, "context", ssl.create_default_context(cafile=tls[0]))
    client = HttpJsonClient(
        "torrcast/test",
        lambda host: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))],
    )
    port = server.server_address[1]
    try:
        assert client.fetch(f"https://127.0.0.1:{port}/poster.jpg", 10.0) == _Store.poster
        assert _Store.seen == ["torrcast/test"], f"склад увидел {_Store.seen}"

        with pytest.raises(OSError, match="404"):
            client.fetch(f"https://127.0.0.1:{port}/no-such.jpg", 10.0)
    finally:
        server.shutdown()
        server.server_close()


def test_a_wikipedia_429_holds_the_background_and_lets_the_card_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a 429 with ``Retry-After`` the background waits it out; a click still asks."""
    statuses = [429, 200]
    asked: list[str] = []

    class _Reply:
        def __init__(self) -> None:
            self.status = statuses.pop(0)

        def getheader(self, name: str) -> str | None:
            return "30" if name == "Retry-After" else None

        def read(self) -> bytes:
            return b"{}"

    class _Connection:
        def __init__(self, host: str, **_kwargs: object) -> None:
            self.host = host

        def request(self, *_args: object, **_kwargs: object) -> None:
            asked.append(self.host)

        def getresponse(self) -> _Reply:
            return _Reply()

        def close(self) -> None:
            return None

    monkeypatch.setattr(http_json_client, "_IPv4Connection", _Connection)
    client = HttpJsonClient("torrcast/test")
    with pytest.raises(OSError):
        client.get("ru.wikipedia.org", "/w/api.php", {}, {}, 0.0)
    with pytest.raises(OSError):
        client.get("ru.wikipedia.org", "/w/api.php", {}, {}, 0.0)
    assert client.get("ru.wikipedia.org", "/w/api.php", {}, {}, 0.0, foreground=True) == {}
    assert asked == ["ru.wikipedia.org", "ru.wikipedia.org"]


def test_a_request_broken_on_the_wire_is_trouble_not_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stalled Wikipedia request marks the trouble clock and asks for no quiet window."""

    class _Stalled:
        def __init__(self, host: str, **_kwargs: object) -> None:
            self.host = host

        def request(self, *_args: object, **_kwargs: object) -> None:
            raise TimeoutError("timed out")

        def close(self) -> None:
            return None

    monkeypatch.setattr(http_json_client, "_IPv4Connection", _Stalled)
    client = HttpJsonClient("torrcast/test")
    start = client.calm_at()
    with pytest.raises(OSError):
        client.get("ru.wikipedia.org", "/w/api.php", {}, {}, 1.0)
    assert client.troubled_since(start)
    assert client.calm_at() < start + 1.0


class _Talk(http.server.BaseHTTPRequestHandler):
    """Склад на HTTP/1.1: помнит порт каждого пришедшего соединения; может молча закрыть."""

    protocol_version = "HTTP/1.1"
    ports: ClassVar[list[int]] = []
    hang_up: ClassVar[bool] = False

    def do_GET(self) -> None:
        _Talk.ports.append(self.client_address[1])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")
        self.close_connection = _Talk.hang_up

    def log_message(self, fmt: str, *args: Any) -> None:
        return None


@pytest.mark.machine
def test_requests_to_one_host_share_a_connection_and_survive_its_hang_up(
    tls: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Дома каждое новое соединение теряло SYN и ждало повтора ядра секундами.

    Три запроса подряд идут одним соединением; закрытое сервером молча соединение не
    роняет запрос - он повторяется по новому.
    """
    _Talk.ports, _Talk.hang_up = [], False
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls[0], tls[1])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), _Talk)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True, name="talk").start()
    monkeypatch.setattr(_IPv4Connection, "context", ssl.create_default_context(cafile=tls[0]))
    client = HttpJsonClient(
        "torrcast/test",
        lambda host: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))],
    )
    where = f"127.0.0.1:{server.server_address[1]}"
    try:
        for _ in range(3):
            assert client.get(where, "/w/api.php", {}, {}, 10.0) == {}
        assert len(set(_Talk.ports)) == 1, f"три запроса открыли {len(set(_Talk.ports))} соединения"

        _Talk.hang_up = True
        assert client.get(where, "/w/api.php", {}, {}, 10.0) == {}
        assert client.get(where, "/w/api.php", {}, {}, 10.0) == {}
        assert len(set(_Talk.ports)) == 2
    finally:
        server.shutdown()
        server.server_close()
