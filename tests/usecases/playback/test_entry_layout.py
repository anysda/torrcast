"""Зеркало раскладки по записи: ровно :func:`layout` с полями записи."""

from __future__ import annotations

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.playback.entry_layout import entry_layout
from torrcast.usecases.playback.layout import layout
from torrcast.usecases.playback.media_grid import MediaGrid

_SOURCE = "file:///нет-такого"


def _spans(grid: MediaGrid) -> list[float]:
    """Длины всех кусков сетки."""
    return [grid.span(k) for k in range(grid.count)]


def test_the_entry_layout_is_layout_with_the_entry_fields() -> None:
    """HEVC без паспортного веса: вес из записи (оценка по размеру) доходит до перекода."""
    config = Config(recode=True)
    entry = Entry(
        title="Футурама", magnet="magnet:?x", dur=1352.9, vbps=0.54, codec="hevc",
        depth=8, frame=720,
    )  # fmt: skip

    grid, whole = entry_layout(config, _SOURCE, entry, CAUTIOUS, 91_000_000)
    want_grid, want_whole = layout(
        config, _SOURCE, 1352.9, "hevc", 0.54, depth=8, profile=CAUTIOUS, frame=720,
        file_size=91_000_000,
    )  # fmt: skip

    assert (whole, _spans(grid)) == (want_whole, _spans(want_grid))


def test_an_unknown_weight_reaches_layout_as_zero() -> None:
    """``-1`` в записи - «веса нет», а не отрицательный битрейт."""
    config = Config(recode=True)
    entry = Entry(title="Фильм", magnet="magnet:?x", dur=300.0, vbps=-1.0, codec="av1", depth=8)

    _grid, whole = entry_layout(config, _SOURCE, entry)
    _want_grid, want_whole = layout(config, _SOURCE, 300.0, "av1", 0.0, depth=8)

    assert whole == want_whole
