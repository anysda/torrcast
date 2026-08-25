"""Зеркало общего места показа: слово корня видят все части сценария разом."""

from __future__ import annotations

from pathlib import Path

import pytest

import torrcast.usecases.playback._show_state as _state
from tests.fakes import composition
from torrcast.runtime.wire import wire
from torrcast.usecases.playback._show_state import _configure_playback
from torrcast.usecases.playback.show_environment import ShowEnvironment


def test_every_slot_of_the_show_is_filled_by_the_composition_root() -> None:
    """Корень заполняет ВСЕ объявленные слоты: молчаливой подделки у медиатракта нет."""
    wire()

    assert [name for name in _state.__annotations__ if not hasattr(_state, name)] == []


def test_the_word_of_the_composition_reaches_the_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слот берёт то, что положил корень, и берёт это КАЖДЫЙ раз, а не на импорте."""
    started: list[str] = []
    composition.use_start_unit(monkeypatch, started.append)

    _state.start_play_unit("кино")

    assert started == ["кино"]


def test_a_second_word_replaces_the_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Корень сказал заново - показ берёт новое, а не первое."""
    wire()
    previous = _state.start_play_unit
    first: list[str] = []
    second: list[str] = []
    try:
        composition.use_start_unit(monkeypatch, first.append)
        _configure_playback(
            ShowEnvironment(
                clock=_state.CLOCK,
                receivers=_state.make_receiver,
                prober=_state.probe,
                detect=_state.detect_profile,
                video_pick=_state.pick_video_file,
                out_dir=_state.hls_dir,
                base_url=_state.hls_base,
                flag=_state.playing_flag,
                forget_flag=_state.forget_playing,
                start_unit=second.append,
                keys=_state.film_keys,
                grid=_state.grid_for,
                server=_state.HlsServer,
                encode=_state.Encode,
                recoder=_state.Recoder,
                weights=_state.weights_of,
                flat=_state.flat_weights,
                whole=_state.whole_encode,
                maxrate_gain=_state.MAXRATE_GAIN,
                recode_dir=_state.RECODE_DIR,
            )
        )
        _state.start_play_unit("кино")

        assert (first, second) == ([], ["кино"])
    finally:
        _state.start_play_unit = previous


def test_the_show_knows_where_its_pieces_live() -> None:
    """Каталог перекодированного и потолок кодера - числа корня, а не догадки показа."""
    wire()

    assert isinstance(_state.RECODE_DIR, str) and _state.RECODE_DIR
    assert _state.MAXRATE_GAIN > 1.0
    assert isinstance(_state.hls_dir("/tmp/hls-зеркало"), Path)
