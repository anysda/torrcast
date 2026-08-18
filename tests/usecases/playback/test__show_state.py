"""Зеркало общего места показа: слово корня видят все части сценария разом."""

from __future__ import annotations

from pathlib import Path

import pytest

import torrcast.usecases.playback._show_state as _state
from torrcast.runtime.wire import wire
from torrcast.usecases.playback._show_state import _configure_playback


def test_every_slot_of_the_show_is_filled_by_the_composition_root() -> None:
    """Корень заполняет ВСЕ объявленные слоты: молчаливой подделки у медиатракта нет."""
    wire()

    assert [name for name in _state.__annotations__ if not hasattr(_state, name)] == []


def test_the_word_of_the_composition_reaches_the_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слот берёт то, что положил корень, и берёт это КАЖДЫЙ раз, а не на импорте."""
    started: list[str] = []
    monkeypatch.setattr(_state, "start_play_unit", started.append)

    _state.start_play_unit("кино")

    assert started == ["кино"]


def test_a_second_word_replaces_the_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Корень сказал заново - показ берёт новое, а не первое."""
    wire()
    previous = _state.start_play_unit
    first: list[str] = []
    second: list[str] = []
    try:
        monkeypatch.setattr(_state, "start_play_unit", first.append)
        _configure_playback(
            _state.CLOCK,
            _state.make_receiver,
            _state.probe,
            _state.detect_profile,
            _state.pick_video_file,
            _state.hls_dir,
            _state.hls_base,
            _state.playing_flag,
            _state.forget_playing,
            second.append,
            _state.film_keys,
            _state.grid_for,
            _state.HlsServer,
            _state.Encode,
            _state.Recoder,
            _state.weights_of,
            _state.whole_encode,
            _state.MAXRATE_GAIN,
            _state.RECODE_DIR,
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
