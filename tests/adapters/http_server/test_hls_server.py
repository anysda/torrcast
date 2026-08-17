"""Проверяет живую раздачу: заголовки, диапазоны, 404 и молчание после остановки."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from tests.conftest import free_port
from torrcast.adapters.http_server.hls_server import HlsServer


class _Supply:
    """Поставщик сегментов на время проверки: манифест из головы, один кусок с диска."""

    def __init__(self, out: Path) -> None:
        self.out = out

    def manifest(self) -> bytes:
        return b"#EXTM3U\n#EXT-X-ENDLIST\n"

    def segment(self, slot: int) -> Path | None:
        piece = self.out / f"v{slot}.ts"
        return piece if piece.exists() else None


@pytest.fixture
def serving(tmp_path: Path) -> object:
    (tmp_path / "v0.ts").write_bytes(bytes(range(256)) * 4)
    server = HlsServer(tmp_path, port=free_port(), feed=_Supply(tmp_path))
    server.start()
    try:
        yield f"http://127.0.0.1:{server.port}"
    finally:
        server.stop()


@pytest.mark.machine
def test_every_answer_carries_cors_and_is_never_cached(serving: str) -> None:
    """Без ``Access-Control-Allow-Origin: *`` Chromecast молча не играет.

    Кэшировать нельзя ничего: после перепаковки под теми же именами лежит другое место
    фильма, и кэш приёмника показал бы старое.
    """
    for path in ("index.m3u8", "v0.ts", "нет-такого"):
        answer = requests.get(f"{serving}/{path}", timeout=10)
        assert answer.headers["Access-Control-Allow-Origin"] == "*", path
        assert answer.headers["Cache-Control"] == "no-store", path
        assert answer.headers["Accept-Ranges"] == "bytes", path


@pytest.mark.machine
def test_the_manifest_and_the_segment_come_from_the_feed_and_nothing_else_does(
    serving: str,
) -> None:
    """Отдаётся ровно сетка: манифест на весь фильм и куски, которые в ней названы."""
    manifest = requests.get(f"{serving}/index.m3u8", timeout=10)
    assert manifest.status_code == 200
    assert manifest.headers["Content-Type"] == "application/vnd.apple.mpegurl"
    assert manifest.content == b"#EXTM3U\n#EXT-X-ENDLIST\n"

    piece = requests.get(f"{serving}/v0.ts", timeout=10)
    assert piece.status_code == 200 and len(piece.content) == 1024
    assert piece.headers["Content-Type"] == "video/mp2t"

    assert requests.get(f"{serving}/v9.ts", timeout=10).status_code == 404
    assert requests.get(f"{serving}/../state.json", timeout=10).status_code == 404


@pytest.mark.machine
def test_a_piece_is_re_asked_by_range(serving: str) -> None:
    """Q70D переспрашивает куски диапазонами; за краем куска - 416, а не весь кусок."""
    part = requests.get(f"{serving}/v0.ts", headers={"Range": "bytes=10-19"}, timeout=10)
    assert part.status_code == 206
    assert part.headers["Content-Range"] == "bytes 10-19/1024"
    assert len(part.content) == 10

    over = requests.get(f"{serving}/v0.ts", headers={"Range": "bytes=5000-6000"}, timeout=10)
    assert over.status_code == 416
    assert over.headers["Content-Range"] == "bytes */1024"


@pytest.mark.machine
def test_a_stopped_serving_really_goes_quiet(tmp_path: Path) -> None:
    """⚠️ «Раздача остановлена» обязано значить «раздача молчит».

    Приёмник держит одно keep-alive соединение на весь показ; переживи оно остановку -
    LOAD следующей серии уехал бы в тот же сокет и получил манифест прошлой.
    """
    (tmp_path / "v0.ts").write_bytes("кусок".encode())
    server = HlsServer(tmp_path, port=free_port(), feed=_Supply(tmp_path))
    server.start()
    keep = requests.Session()
    assert keep.get(f"http://127.0.0.1:{server.port}/v0.ts", timeout=10).status_code == 200
    server.stop()

    with pytest.raises(requests.RequestException):
        keep.get(f"http://127.0.0.1:{server.port}/v0.ts", timeout=10)
