"""Зеркало завода раздачи: показ поднимает её ровно теми доводами, что объявил."""

from __future__ import annotations

from pathlib import Path

from torrcast.stream import HlsServer
from torrcast.usecases.playback.stream_server import StreamServer
from torrcast.usecases.playback.stream_servers import StreamServers


def test_the_real_factory_answers_the_named_contract(tmp_path: Path) -> None:
    """Каталог, серт и лента - те же доводы, которыми показ заводит раздачу."""
    named: StreamServers = HlsServer

    made: StreamServer = named(tmp_path, "", "", port=0, tls=False, feed=None)

    made.start()
    made.stop()
