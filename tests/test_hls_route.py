"""HLS страницы: тот же origin снаружи, живой сервер показа на петле внутри."""

from __future__ import annotations

import http.server
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from hass.serve import serve
from torrcast.domain.config import Config

MANIFEST = b"#EXTM3U\n#EXTINF:10,\nv0.ts\n"
SEGMENT = bytes(range(256)) * 4096


#: Что дошло до сервера показа: дверь страницы обязана отсечь чужое имя сама.
ASKED: list[str] = []


class _Hls(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        ASKED.append(self.path)
        bodies = {"/index.m3u8": MANIFEST, "/v0.ts": SEGMENT}
        body = bodies.get(self.path)
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        first, last, code = 0, len(body) - 1, 200
        if self.headers.get("Range") == "bytes=10-19":
            first, last, code = 10, 19, 206
        sent = body[first : last + 1]
        kind = "application/vnd.apple.mpegurl" if self.path.endswith(".m3u8") else "video/mp2t"
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(sent)))
        self.send_header("Accept-Ranges", "bytes")
        if code == 206:
            self.send_header("Content-Range", f"bytes {first}-{last}/{len(body)}")
        self.end_headers()
        self.wfile.write(sent)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


@pytest.fixture
def hls_port() -> Iterator[int]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def page(hls_port: int, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setattr("web.hls.load_config", lambda: Config(hls_port=hls_port))
    server = serve(object(), 0, "127.0.0.1")  # type: ignore[arg-type]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.machine
def test_the_page_serves_the_manifest_and_segment_from_its_own_origin(page: str) -> None:
    with urllib.request.urlopen(f"{page}/hls/index.m3u8", timeout=5) as manifest:
        assert (manifest.status, manifest.read(), manifest.headers["Content-Type"]) == (
            200,
            MANIFEST,
            "application/vnd.apple.mpegurl",
        )
    with urllib.request.urlopen(f"{page}/hls/v0.ts", timeout=5) as segment:
        assert (segment.status, len(segment.read())) == (200, len(SEGMENT))


@pytest.mark.machine
def test_a_byte_range_reaches_the_show_server_and_returns_as_a_range(page: str) -> None:
    request = urllib.request.Request(f"{page}/hls/v0.ts", headers={"Range": "bytes=10-19"})
    with urllib.request.urlopen(request, timeout=5) as answer:
        assert (answer.status, answer.read()) == (206, SEGMENT[10:20])
        assert answer.headers["Content-Range"] == f"bytes 10-19/{len(SEGMENT)}"


@pytest.mark.parametrize(
    "path", ["state.json", "../state.json", "%2e%2e/state.json", "v0.ts/../../state.json"]
)
@pytest.mark.machine
def test_the_hls_door_never_exposes_another_file(page: str, path: str) -> None:
    ASKED.clear()
    with pytest.raises(urllib.error.HTTPError) as refusal:
        urllib.request.urlopen(f"{page}/hls/{path}", timeout=5)
    assert refusal.value.code == 404
    assert ASKED == [], "чужое имя ушло серверу показа мимо двери страницы"


@pytest.mark.machine
def test_a_stopped_show_server_is_a_gateway_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    held = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hls)
    port = int(held.server_address[1])
    held.server_close()
    monkeypatch.setattr("web.hls.load_config", lambda: Config(hls_port=port))
    server = serve(object(), 0, "127.0.0.1")  # type: ignore[arg-type]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError) as refusal:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_address[1]}/hls/index.m3u8", timeout=5
            )
        assert refusal.value.code == 502
    finally:
        server.shutdown()
        server.server_close()
