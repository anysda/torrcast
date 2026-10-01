"""A CDN edge that freezes every body after its first bytes must not hold the name for long."""

from __future__ import annotations

import http.server
import socket
import ssl
import threading
import time
from typing import Any, ClassVar

import pytest

from tests.conftest import free_port
from torrcast.adapters.wiki.http_json_client import BODY_SILENCE, HttpJsonClient, _IPv4Connection


class _Edge(http.server.BaseHTTPRequestHandler):
    """Promises a poster; on the frozen edge sends its first bytes and goes silent."""

    frozen: ClassVar[bool] = False
    thaw: ClassVar[threading.Event] = threading.Event()
    poster: ClassVar[bytes] = b"\xff\xd8\xff\xe0" + b"poster" * 200

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", str(len(_Edge.poster)))
        self.end_headers()
        if self.frozen:
            self.wfile.write(_Edge.poster[:16])
            self.wfile.flush()
            _Edge.thaw.wait(10.0)
            return
        self.wfile.write(_Edge.poster)

    def log_message(self, fmt: str, *args: Any) -> None:
        return None


class _Frozen(_Edge):
    frozen = True


@pytest.mark.machine
def test_a_frozen_edge_costs_one_request_not_the_whole_ttl(
    tls: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The name answers the frozen edge first: its body silence ends the fetch well before the
    timeout, and the next fetch asks the name again and goes to the live edge.

    The stand met it live: two of six edges of the poster CDN froze each body at 16 KB, and
    the remembered address starved every IMDb cover of a cold start for ten minutes.
    """
    port = free_port()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls[0], tls[1])
    servers = []
    for host, handler in (("127.0.0.2", _Frozen), ("127.0.0.1", _Edge)):
        server = http.server.ThreadingHTTPServer((host, port), handler)
        server.daemon_threads = False  # server_close joins the frozen handler
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True, name=f"edge-{host}").start()
        servers.append(server)
    monkeypatch.setattr(_IPv4Connection, "context", ssl.create_default_context(cafile=tls[0]))
    edges = ("127.0.0.2", "127.0.0.1")
    answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in edges]
    client = HttpJsonClient("torrcast/test", lambda host: answer)
    address = f"https://127.0.0.1:{port}/poster.jpg"
    _Edge.thaw.clear()
    try:
        began = time.monotonic()
        with pytest.raises(TimeoutError):
            client.fetch(address, 8.0)
        spent = time.monotonic() - began
        assert spent < BODY_SILENCE + 1.0, f"a frozen body held the fetch {spent:.1f} s"
        assert client.fetch(address, 8.0) == _Edge.poster
    finally:
        _Edge.thaw.set()
        for server in servers:
            server.shutdown()
            server.server_close()
