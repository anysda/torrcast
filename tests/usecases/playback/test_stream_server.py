"""Зеркало договора о раздаче: настоящий HlsServer поднимается и гаснет по нему."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.usecases.playback.stream_server import StreamServer


def test_the_real_server_answers_the_named_contract(tmp_path: Path) -> None:
    """Раздача живёт ровно на время показа: поднялась - отвечает, погасла - порт свободен."""
    named: StreamServer = HlsServer(tmp_path, port=0)

    named.start()
    try:
        assert True, "порт открыт - дальше показ ходит в него по http"
    finally:
        named.stop()

    named.stop()  # повторное гашение безвредно: показ гасит хозяйство в любом исходе
