"""Зеркало ленты с концом: список рисуется после ``settle``, часы показа ведут поздний конец."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from tests.usecases.feed_pack.world import feed, grid
from torrcast.domain.segment_container import FMP4
from torrcast.usecases.playback.ended_feed import EndedFeed

if TYPE_CHECKING:
    from pathlib import Path


def test_the_playlist_is_drawn_after_the_end_is_settled(tmp_path: Path) -> None:
    """Приёмник берёт список один раз: длина в нём обязана быть уже по картинке."""
    show = cast(EndedFeed, feed(tmp_path, kind=EndedFeed, grid=grid(60.0, 10.0)))
    asked: list[str] = []

    def settle() -> None:
        asked.append("settle")
        show.grid = grid(55.0, 10.0)

    show.settle = settle

    body = show.manifest().decode("utf-8")

    assert asked == ["settle"]
    assert body == grid(55.0, 10.0).manifest()


def test_the_master_of_fmp4_waits_for_the_end_too(tmp_path: Path) -> None:
    """У fMP4 первым идёт главный список: ждать конца на нём, медийный придёт уже по сетке."""
    show = cast(EndedFeed, feed(tmp_path, kind=EndedFeed, container=FMP4))
    asked: list[str] = []
    show.settle = lambda: asked.append("settle")

    show.manifest()

    assert asked == ["settle"]


def test_without_an_ending_it_is_the_plain_feed(tmp_path: Path) -> None:
    show = feed(tmp_path, kind=EndedFeed)

    assert show.manifest().decode("utf-8") == show.grid.manifest()


def test_the_show_clock_carries_the_late_end(tmp_path: Path) -> None:
    """Поздний паспорт ведёт уборка по часам показа, а погасшая лента его больше не зовёт."""
    show = cast(EndedFeed, feed(tmp_path, kind=EndedFeed))
    ticks: list[str] = []
    show.tick = lambda: ticks.append("tick")

    show.sweep()
    show.stop()
    show.sweep()

    assert ticks == ["tick"]
