"""Зеркало сборки сетки: одно решение о перекоде и одна сетка - у показа и у прогрева."""

from __future__ import annotations

import pytest

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.recode import MAXRATE_GAIN, whole_encode
from torrcast.stream import grid_for
from torrcast.usecases.playback._layout import _layout


@pytest.fixture(autouse=True)
def _tract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_state, "whole_encode", whole_encode)
    monkeypatch.setattr(_state, "grid_for", grid_for)
    monkeypatch.setattr(_state, "MAXRATE_GAIN", MAXRATE_GAIN)


def test_the_same_passport_gives_the_same_layout_twice() -> None:
    """Показ и прогрев считают это порознь и обязаны получить одно и то же - до знака."""
    args = (Config(), "file:///нет-такого", 300.0, "h264", 5.0)

    first_grid, first_whole = _layout(*args, depth=8, profile=CAUTIOUS)
    second_grid, second_whole = _layout(*args, depth=8, profile=CAUTIOUS)

    assert first_grid.count == second_grid.count
    assert [first_grid.span(k) for k in range(first_grid.count)] == [
        second_grid.span(k) for k in range(second_grid.count)
    ]
    assert (first_whole, second_whole) == (None, None)


def test_the_whole_recode_is_decided_before_the_grid() -> None:
    """Под сплошным перекодом вес куска задаём МЫ - и сетка это уже знает."""
    config = Config(recode=True)

    _grid, whole = _layout(
        config, "file:///нет-такого", 300.0, "av1", 21.0, depth=8, profile=CAUTIOUS
    )

    assert whole is not None, "чужой кодек обязан решиться перекодом до всякой сетки"


def test_the_say_handle_hears_the_grid_talking() -> None:
    """Подмена нарезки не молчаливая: ручка слова получает свою строку."""
    said: list[str] = []

    _layout(Config(), "file:///нет-такого", 300.0, "h264", 5.0, say=said.append)

    assert said, "сетка без карты обязана сказать об этом вслух"
