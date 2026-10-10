"""Зеркало подписи прогретых кусков: боевая раздача её умеет, и обработчик видит новую."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.usecases.playback._relabel import _Relabel

if TYPE_CHECKING:
    from pathlib import Path


def test_the_live_server_takes_a_new_label_set(tmp_path: Path) -> None:
    """Пересборка сетки меняет хранилище прогрева: подпись в следе обязана идти по новому."""
    server = HlsServer(tmp_path, host="127.0.0.1", port=0)
    assert isinstance(server, _Relabel)
    server.start()
    try:
        server.relabel({7, 8})
        assert server.warm_recodes == {7, 8}
        assert server._bound is not None and server._bound.warm_recodes == {7, 8}
    finally:
        server.stop()


def test_a_server_not_started_keeps_the_label_for_its_start(tmp_path: Path) -> None:
    server = HlsServer(tmp_path, host="127.0.0.1", port=0)

    server.relabel({3})

    assert server.warm_recodes == {3}
