"""The shelf tile's circle waits out the viewer's search and is counted as the warmup's."""

from __future__ import annotations

import contextlib
from functools import partial

import pytest

from torrcast.adapters.prowlarr.host_slots import QUIET, HostSlots
from torrcast.adapters.prowlarr.warmup import WARMUP
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.shelf_circle import shelf_circle
from web.warm_cache import WarmCache

_MOVIE = Picture(title="Interstellar", year=2014, kind="movie")
_MOVIE.releases = [Release(raw_name="Interstellar 2014 BDRip 1080p", title="Interstellar")]
_PLAN = Plan(picture=_MOVIE, ranked=list(_MOVIE.releases), runtime=8520.0, warn_mbit=12.0)


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _Stand:
    """A cache, its host slots and a sleep that moves the clock; the circle logs its calls."""

    def __init__(self, found: bool = True) -> None:
        self.clock = _Clock()
        self.slots = HostSlots(self.clock)
        self.found = found
        self.asked: list[tuple[float, bool, bool]] = []  # time, warmup's, seat held
        self.slept = 0.0
        self.wake: contextlib.ExitStack | None = None  # the viewer's search ends at first sleep
        self.cache = WarmCache(circle=self._circle, blurbs=lambda _p: None, spawn=lambda j: j())

    def _circle(self, query: str) -> list[Plan]:
        seat = self.cache._seats.get(query.strip()) is not None
        self.asked.append((self.clock.now, WARMUP.get(), seat))
        if not self.found:
            raise NotFoundError(query)
        return [_PLAN]

    def sleep(self, secs: float) -> None:
        self.slept += secs
        self.clock.now += secs
        if self.wake is not None:
            self.wake.close()
            self.wake = None

    def run(self, query: str = "Interstellar") -> list[Plan]:
        return shelf_circle(self.cache, query, self.slots, self.clock, self.sleep)


def test_right_after_the_start_the_shelf_counts_at_once_as_the_warmup() -> None:
    stand = _Stand()
    assert stand.run() == [_PLAN]
    assert stand.slept == 0.0, "no viewer searched yet: the shelf fills at once"
    assert stand.asked == [(100.0, True, True)], "the warmup's circle a viewer can take over"
    assert not stand.cache._seats
    assert not stand.cache._busy


def test_the_shelf_waits_out_the_viewers_search_and_the_quiet_after_it() -> None:
    stand = _Stand()
    stand.wake = contextlib.ExitStack()
    stand.wake.enter_context(stand.slots.live())
    assert stand.run() == [_PLAN]
    [(at, warmups, _seat)] = stand.asked
    assert warmups
    assert at >= 100.0 + QUIET, "the shelf stood in Prowlarr ahead of the viewer's text"


def test_a_search_ended_long_ago_does_not_hold_the_shelf() -> None:
    stand = _Stand()
    with stand.slots.live():
        pass
    stand.clock.now += QUIET
    stand.run()
    assert stand.slept == 0.0


def test_a_counted_tile_answers_from_memory_even_during_a_search() -> None:
    stand = _Stand()
    stand.run()
    with stand.slots.live():
        assert stand.run() == [_PLAN]
    assert len(stand.asked) == 1
    assert stand.slept == 0.0


def test_a_tile_found_nowhere_is_refused_as_before() -> None:
    stand = _Stand(found=False)
    with pytest.raises(NotFoundError):
        stand.run()
    with pytest.raises(NotFoundError):
        stand.run()
    assert len(stand.asked) == 1, "the refusal is remembered, the network is not asked twice"


def test_the_shelf_verdict_counts_its_circles_this_way() -> None:
    from web.shelf_playable import PLAYABLE
    from web.warm_wiring import WARM

    circle = PLAYABLE.circle
    assert isinstance(circle, partial)
    assert (circle.func, circle.args) == (shelf_circle, (WARM,))
