"""Зеркало сборки тракта: у упаковки, прогрева и приёмника одна сетка и одно решение."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

import torrcast.usecases.playback._show_state as _state
from tests.usecases.playback.world import film_keys, grid
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from torrcast.recode import Encode, Recoder, Weights, whole_encode
from torrcast.stream import HlsServer, hls_dir
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
    monkeypatch.setattr(_state, "film_keys", lambda source: film_keys())
    monkeypatch.setattr(_state, "weights_of", Weights.of)
    monkeypatch.setattr(_state, "Recoder", Recoder)
    monkeypatch.setattr(_state, "Encode", Encode)
    monkeypatch.setattr(_state, "whole_encode", whole_encode)
    monkeypatch.setattr(_state, "HlsServer", HlsServer)
    monkeypatch.setattr(_state, "RECODE_DIR", "recode")
    monkeypatch.setattr(_state, "hls_dir", lambda where: hls_dir(str(where)))


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
    layout = grid()

    recoder, warmer, feed, server, _receiver = _tract(
        _config(tmp_path), "http://ts", 0, "кино", out, layout, None, 0.0, 8.0, False, _Cutting()
    )
    try:
        assert feed.grid is layout
        assert warmer is not None and warmer.grid is layout
        assert recoder is not None and cast(Recoder, recoder).grid is layout
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
