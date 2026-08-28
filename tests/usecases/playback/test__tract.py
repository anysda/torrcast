"""Зеркало сборки тракта: у упаковки, прогрева и приёмника одна сетка и одно решение."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

import torrcast.adapters.http_server.hls_server as hls_server
import torrcast.usecases.feed_pack.feed_segment as feed_segment
from tests.usecases.playback.world import grid
from tests.usecases.warm.test_run import _Encode, _Packer
from tests.usecases.warm.test_run import _tract as run_tract
from tests.usecases.warm.world import world as warm_world
from torrcast.adapters.http_server._handler import _Handler
from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.adapters.http_server.log_segment import log_segment
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.whole_encode import whole_encode
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from torrcast.domain.trace_sources import WARMED_RECODE
from torrcast.ports.journal.slot import install
from torrcast.ports.recode.encoding import Encoding
from torrcast.usecases.playback._tract import _tract
from torrcast.usecases.warm.run import _run


class _Cutting:
    """Приёмник, который спотыкается о сетку: у него есть ручка границы куска."""

    next_cut: Callable[[float], float] | None = None

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        raise AssertionError("сборка тракта приёмник о месте не спрашивает")


@pytest.fixture(autouse=True)
def _world(monkeypatch: pytest.MonkeyPatch) -> None:
    """Единственная подделка тракта - карта опорных кадров; остальное настоящее.

    Раздача, оба кодировщика и каталог перекода приезжают от корня
    (:func:`torrcast.runtime.wire.wire`) теми же, что стоят на боевом пути: договор
    медиатракта зеркало сверяет с ними, а не с пересказом.
    """


def _config(tmp_path: Path) -> Config:
    return Config(
        recode=True,
        warm=True,
        warm_dir=str(tmp_path / "warm"),
        hls_dir=str(tmp_path / "hls"),
        hls_port=0,
    )


def test_the_pack_and_the_warm_up_get_the_same_grid(tmp_path: Path) -> None:
    """Куски приёмнику приходят из двух мест, и сетка у обоих обязана быть одна."""
    out = hls_dir(str(tmp_path / "hls"))
    grid_of = grid()

    recoder, warmer, feed, server, _receiver = _tract(
        _config(tmp_path), "http://ts", 0, "кино", out, grid_of, None, 0.0, 8.0, False, _Cutting()
    )
    try:
        assert feed.grid is grid_of
        assert warmer is not None and warmer.grid is grid_of
        assert recoder is not None and cast(Recoder, recoder).grid is grid_of
    finally:
        server.stop()


def test_the_whole_recode_leaves_no_spot_recoder(tmp_path: Path) -> None:
    """Перекодировать поверх перекода нечего: точечный кодировщик не поднимается вовсе."""
    out = hls_dir(str(tmp_path / "hls"))
    whole = whole_encode(9.0)

    recoder, warmer, feed, server, _receiver = _tract(
        _config(tmp_path), "http://ts", 0, "кино", out, grid(), whole, 0.0, 8.0, False, _Cutting()
    )
    try:
        assert recoder is None
        assert feed.encode is whole
        assert warmer is not None and warmer.encode is whole
    finally:
        server.stop()


def test_the_grid_is_named_to_the_receiver_that_measures_by_it(tmp_path: Path) -> None:
    """Приёмник живёт весь юнит, а сетка у каждой серии своя - и её называют каждой."""
    out = hls_dir(str(tmp_path / "hls"))
    receiver = _Cutting()

    _recoder, _warmer, _feed, server, given = _tract(
        _config(tmp_path), "http://ts", 0, "кино", out, grid(), None, 0.0, 8.0, False, receiver
    )
    try:
        assert given is receiver
        cut = receiver.next_cut
        assert cut is not None and cut(35.0) == 40.0
    finally:
        server.stop()


def test_a_spot_marked_after_serving_started_is_named_as_a_warmed_recode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Лента одного показа видит живую метку прогрева без чтения диска на выдаче."""

    class _ServerWithoutSocket:
        """Старт раздачи с настоящей привязкой обработчика, но без сокета машины."""

        def __init__(self, _address: object, handler: type[_Handler]) -> None:
            self.RequestHandlerClass = handler
            self.ctx: object | None = None

        def serve_forever(self, poll_interval: float = 0.2) -> None:
            assert poll_interval == 0.2
            return None

        def shutdown(self) -> None:
            return None

        def server_close(self) -> None:
            return None

        def drop_live(self) -> None:
            return None

    monkeypatch.setattr(hls_server, "_Server", _ServerWithoutSocket)
    monkeypatch.setattr(feed_segment, "segment_start", lambda _path: 20.0)
    out = hls_dir(str(tmp_path / "hls"))
    _recoder, warmer, _feed, server, _receiver = _tract(
        _config(tmp_path), "http://ts", 0, "кино", out, grid(), None, 0.0, 8.0, False, _Cutting()
    )
    sink = Mock()
    install(sink)
    assert warmer is not None
    warmer.vault.open()
    serving = cast(HlsServer, server)
    serving.start()
    try:
        packers: list[_Packer] = []
        parts, _commands = run_tract(packers)
        warm_world(lay_spot=lambda *_args: True, **parts)
        warmer.spot_encode = cast(Encoding, _Encode())
        _run(warmer, 2, 2, spot=True, began_of=lambda _path: 20.0)
        body = warmer.vault.path(2).read_bytes()
        assert serving._server is not None
        handler_type = cast(type[_Handler], serving._server.RequestHandlerClass)
        handler = object.__new__(handler_type)
        assert handler._read("v2.ts") == body
        log_segment("v2.ts", 0.0, len(body), 0.0, handler._src)

        tape: list[dict[str, Any]] = [sink.segment.call_args.kwargs]
        assert tape[-1]["src"] == WARMED_RECODE
    finally:
        serving.stop()
