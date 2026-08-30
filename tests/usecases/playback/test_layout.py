"""Зеркало сборки сетки: одно решение о перекоде и одна сетка - у показа и у прогрева."""

from __future__ import annotations

import pytest

from tests.fakes.composition import use_media_grid
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.usecases.playback.layout import layout
from torrcast.usecases.playback.media_grid import MediaGrid


def test_the_same_passport_gives_the_same_layout_twice() -> None:
    """Показ и прогрев считают это порознь и обязаны получить одно и то же - до знака."""
    args = (Config(), "file:///нет-такого", 300.0, "h264", 5.0)

    first_grid, first_whole = layout(*args, depth=8, profile=CAUTIOUS)
    second_grid, second_whole = layout(*args, depth=8, profile=CAUTIOUS)

    assert first_grid.count == second_grid.count
    assert [first_grid.span(k) for k in range(first_grid.count)] == [
        second_grid.span(k) for k in range(second_grid.count)
    ]
    assert (first_whole, second_whole) == (None, None)


def test_the_whole_recode_is_decided_before_the_grid() -> None:
    """Под сплошным перекодом вес куска задаём МЫ - и сетка это уже знает."""
    config = Config(recode=True)

    _grid, whole = layout(
        config, "file:///нет-такого", 300.0, "av1", 21.0, depth=8, profile=CAUTIOUS
    )

    assert whole is not None, "чужой кодек обязан решиться перекодом до всякой сетки"


def test_the_say_handle_hears_the_grid_talking() -> None:
    """Подмена нарезки не молчаливая: ручка слова получает свою строку."""
    said: list[str] = []

    layout(Config(), "file:///нет-такого", 300.0, "h264", 5.0, say=said.append)

    assert said, "сетка без карты обязана сказать об этом вслух"


def test_four_k_tonemap_says_its_measured_cost() -> None:
    """Включённый тонемап на 4К-пути не выглядит бесплатным улучшением цвета."""
    said: list[str] = []

    layout(
        Config(recode_tonemap=True),
        "file:///нет-такого",
        300.0,
        "hevc",
        20.0,
        say=said.append,
        depth=10,
        frame=2160,
        hdr=True,
    )

    assert phrase("playback.tonemap_no_headroom") in said


def test_the_layout_hands_the_receiver_ceilings_to_the_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Оба потолка приёмника - вес и длина - едут в сетку из профиля, а не из умолчания."""
    seen: dict[str, float] = {}

    def spy(source_url: str, duration: float, *args: object, **kwargs: float) -> MediaGrid:
        seen.update(kwargs)
        return grid_for(source_url, duration, *args, **kwargs)  # type: ignore[arg-type]

    use_media_grid(monkeypatch, spy)

    layout(Config(), "file:///нет-такого", 300.0, "h264", 5.0, depth=8, profile=ANDROID_TV)

    assert seen["cap"] == ANDROID_TV.max_segment_bytes
    assert seen["span_cap"] == ANDROID_TV.max_segment_seconds > 0.0
