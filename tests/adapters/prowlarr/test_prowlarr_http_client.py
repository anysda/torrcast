"""Проверяет HTTP-механику Prowlarr на подставленных ответах."""

import contextlib
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.prowlarr_http_client import ProwlarrHttpClient


class _Response:
    def __init__(self) -> None:
        self.closed = False

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return {"rows": 3}

    def close(self) -> None:
        self.closed = True


class _Session:
    def __init__(self) -> None:
        self.timeout = 0.0
        self.posted: tuple[str, object, float] | None = None
        self.response = _Response()
        self.post_response = _Response()

    def get(self, url: str, timeout: float) -> _Response:
        self.timeout = timeout
        return self.response

    def post(self, url: str, json: object, timeout: float) -> _Response:
        self.posted = (url, json, timeout)
        return self.post_response


def test_исполняет_запрос_с_переданным_таймаутом() -> None:
    session = _Session()
    payload = ProwlarrHttpClient().get_json(
        session, "http://prowlarr/search", 3.0, "http://prowlarr"
    )
    assert payload == {"rows": 3}
    assert session.timeout == 3.0
    assert session.response.closed


def test_лечит_индексер_с_назначенными_правилом_таймаутами() -> None:
    session = _Session()
    ProwlarrHttpClient().probe(
        session,
        "http://prowlarr/indexer/7",
        "http://prowlarr/indexer/test",
        15.0,
        10.0,
        "http://prowlarr",
    )
    assert session.timeout == 15.0
    assert session.posted == (
        "http://prowlarr/indexer/test",
        {"rows": 3},
        10.0,
    )
    assert session.response.closed and session.post_response.closed


class _KeepAlive(BaseHTTPRequestHandler):
    """Prowlarr в миниатюре: HTTP/1.1 с keep-alive, простой соединения - секунда.

    Просьбу клиента ``Connection: close`` отражает в ответе, как Kestrel самого Prowlarr.
    """

    protocol_version = "HTTP/1.1"
    timeout = 1.0

    def do_GET(self) -> None:
        self._answer(b"[]")

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._answer(b"")

    def _answer(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if self.headers.get("Connection", "").casefold() == "close":
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _held_sockets(port: int) -> int:
    """Сокеты ЭТОГО процесса, открытые к ``port``: ESTABLISHED или CLOSE-WAIT, по /proc."""
    own = set()
    for fd in os.listdir("/proc/self/fd"):
        with contextlib.suppress(OSError):
            target = os.readlink(f"/proc/self/fd/{fd}")
            if target.startswith("socket:["):
                own.add(target[8:-1])
    held = 0
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        with contextlib.suppress(OSError), open(table) as rows:
            for row in list(rows)[1:]:
                cols = row.split()
                remote_port = int(cols[2].rsplit(":", 1)[1], 16)
                if remote_port == port and cols[3] in ("01", "08") and cols[9] in own:
                    held += 1
    return held


@pytest.mark.machine
@pytest.mark.skipif(
    not os.path.exists("/proc/net/tcp"), reason="сокеты процесса видны только в /proc"
)
def test_a_live_search_session_holds_no_socket_after_its_requests() -> None:
    """Сессия поиска жива, а соединений к Prowlarr за ней не висит - ни открытых, ни CLOSE-WAIT."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _KeepAlive)
    server.daemon_threads = True
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    port = server.server_address[1]
    try:
        api = ProwlarrApi(f"http://127.0.0.1:{port}", "key", timeout=5.0)
        for _ in range(3):
            assert api.get_json(api.url("/api/v1/search")) == []
        api.probe(api.url("/api/v1/indexer/1"), api.url("/api/v1/indexer/test"), 5.0, 5.0)
        # Дольше простоя сервера: пул keep-alive к этой секунде держал бы сокет в CLOSE-WAIT.
        time.sleep(1.5)
        assert api.session is not None
        assert _held_sockets(port) == 0
    finally:
        server.shutdown()
        server.server_close()
        serving.join()
