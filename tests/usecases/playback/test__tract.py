"""Зеркало сборки тракта: у упаковки, прогрева и приёмника одна сетка и одно решение."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from tests.fakes import composition
from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.recode import Recoder, whole_encode
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from torrcast.usecases.playback._tract import _tract


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
    composition.use_film_keys(monkeypatch, lambda source: film_keys())


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
