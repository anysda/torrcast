"""An exhausted source has a deadline even if the receiver keeps saying BUFFERING."""

from pathlib import Path

import pytest

from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import FakeReceiver, feed_with_segments
from torrcast.domain.infra_error import InfraError
from torrcast.domain.position import Position
from torrcast.domain.revive_settings import REVIVE_LIMIT
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.revive_playback._source_wait import _SourceWait


class _BoundedClock(FakeClock):
    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        assert self.now <= REVIVE_LIMIT + 10.0, "the exhausted show waited forever"


class _Buffering(FakeReceiver):
    def position(self, front: float = 0.0) -> Position:
        return Position(89.552858, 7200.0, True, "BUFFERING")


def test_a_missing_continuation_ends_even_without_receiver_error(tmp_path: Path) -> None:
    feed = feed_with_segments(tmp_path, slots=9)
    feed.packer = None
    feed.offline = "the input is silent"
    clock = _BoundedClock()

    with pytest.raises(InfraError, match="next segment"):
        _hold(_Buffering(), feed, clock=clock, start=89.552858)

    assert REVIVE_LIMIT <= clock.now <= REVIVE_LIMIT + 2.0


def test_a_pause_and_real_progress_each_leave_a_full_wait(tmp_path: Path) -> None:
    feed = feed_with_segments(tmp_path, slots=9)
    wait = _SourceWait()
    wait.check(feed, 89.0, False, 0.0)
    wait.check(feed, 89.0, True, REVIVE_LIMIT)
    wait.check(feed, 89.0, False, REVIVE_LIMIT + 1.0)
    wait.check(feed, 89.5, False, 2 * REVIVE_LIMIT)
    wait.check(feed, 89.5, False, 3 * REVIVE_LIMIT - 1.0)

    with pytest.raises(InfraError, match="next segment"):
        wait.check(feed, 89.5, False, 3 * REVIVE_LIMIT)


def test_a_supplied_continuation_is_left_to_the_receiver_watchdog(tmp_path: Path) -> None:
    feed = feed_with_segments(tmp_path, slots=10)
    wait = _SourceWait()

    wait.check(feed, 89.5, False, 0.0)
    wait.check(feed, 89.5, False, REVIVE_LIMIT + 1.0)

    assert wait.since == REVIVE_LIMIT + 1.0
