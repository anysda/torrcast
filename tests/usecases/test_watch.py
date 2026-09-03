"""Зеркально проверяет сторожа позиции показа."""

from torrcast.domain.entry import Entry
from torrcast.usecases.watch import WATCH_SECONDS, Watch


def test_watch_keeps_its_tick_and_its_api() -> None:
    assert WATCH_SECONDS == 10.0
    assert {"see", "close", "flush"} <= set(vars(Watch))


def test_a_live_position_marks_the_bookmark_as_moved_since_this_launch() -> None:
    """Мост Home Assistant честен про паузу ровно настолько, насколько честен этот факт."""
    entry = Entry(title="Кино", magnet="m")
    watch = Watch(key="k", entry=entry, every=999.0)

    watch.see(42.0)

    assert entry.moved is True


def test_a_position_of_zero_or_less_does_not_prove_a_frame_was_shown() -> None:
    entry = Entry(title="Кино", magnet="m")
    watch = Watch(key="k", entry=entry, every=999.0)

    watch.see(0.0)

    assert entry.moved is False
