"""Проверяет предел ранних пересборок: недосчитанная лента не крутит полку каждые пять минут."""

from __future__ import annotations

from web.rebuild_pause import EARLY_TIMES, RebuildPause


def test_a_feed_short_every_time_gets_two_early_rebuilds_then_the_hour() -> None:
    pause = RebuildPause(every=3600.0, soon=300.0)

    pauses = [pause.after(True) for _ in range(EARLY_TIMES + 3)]

    assert EARLY_TIMES == 2
    assert pauses == [300.0, 300.0, 3600.0, 3600.0, 3600.0]


def test_a_whole_feed_starts_the_count_over() -> None:
    pause = RebuildPause(every=3600.0, soon=300.0)
    for _ in range(EARLY_TIMES + 1):
        pause.after(True)

    assert pause.after(False) == 3600.0
    assert [pause.after(True), pause.after(True), pause.after(True)] == [300.0, 300.0, 3600.0]


def test_a_whole_feed_waits_the_hour() -> None:
    assert RebuildPause(every=3600.0, soon=300.0).after(False) == 3600.0
