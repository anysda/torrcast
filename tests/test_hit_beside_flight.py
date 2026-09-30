"""Mirror for a picture judged beside a calm claim while the verdicts are still in flight.

The history asks its covers ahead of the background (``offer(ahead=True)``) but still as a
calm claim: the visible row must judge beside it, the shelf must see the beside verdict as
arriving after the owner lets go, and one empty answer must not be booked as a miss twice.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from hass.hit_posters import FIELD
from tests.test_hit_beside import _TwoPaths
from tests.test_hit_posters import _SETTLE, FakeSource, _hits, _row
from tests.test_late_posters import _until
from torrcast.domain.facts.ask import Ask


class _Gated(FakeSource):
    """Each verdict waits for its own gate; the first answers in silence, the rest name it."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = [threading.Event(), threading.Event()]
        self.opened = [threading.Event(), threading.Event()]
        self.turn = 0

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        turn, self.turn = self.turn, self.turn + 1
        self.entered[turn].set()
        self.opened[turn].wait(_SETTLE)
        return super().wanted(asks, timeout) if turn else {}


class _SilentFirst(_TwoPaths):
    """The calm verdict ends in silence too: an unknown miss, not a real one."""

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        first = self.first
        said = super().wanted(asks, timeout)
        return {} if first else said


@pytest.mark.machine
def test_the_visible_row_judges_beside_a_history_asked_ahead(tmp_path: Path) -> None:
    """Rollback (``ahead`` claims as urgent): the row waits out the history's verdict."""
    source = _TwoPaths()
    hits = _hits(tmp_path, source)
    calm = threading.Thread(target=hits.offer, args=([_row()],), kwargs={"ahead": True})
    calm.start()
    assert source.entered.wait(_SETTLE)
    began = time.monotonic()
    shown = hits.urgent([_row()])[0]
    took = time.monotonic() - began
    source.opened.set()
    calm.join(_SETTLE)
    assert took < 1.0, f"the visible row waited {took:.1f} s for the history's verdict"
    assert isinstance(shown, dict) and FIELD in shown


@pytest.mark.machine
def test_a_beside_verdict_stays_arriving_after_the_owner_lets_go(tmp_path: Path) -> None:
    """Rollback (``arriving`` without the beside set): the shelf stops waiting for a cover."""
    source = _Gated()
    hits = _hits(tmp_path, source)
    calm = threading.Thread(target=hits.offer, args=([_row()],), daemon=True)
    calm.start()
    assert source.entered[0].wait(_SETTLE)
    row = threading.Thread(target=hits.urgent, args=([_row()],), daemon=True)
    row.start()
    assert source.entered[1].wait(_SETTLE)
    source.opened[0].set()
    calm.join(_SETTLE)
    assert hits.arriving([_row()]), "the row's verdict is in flight, the shelf gave up on it"
    source.opened[1].set()
    row.join(_SETTLE)
    assert _until(lambda: hits.landed(_row()))
    assert not hits.arriving([_row()])


@pytest.mark.machine
def test_one_silent_picture_counts_one_unknown_miss(tmp_path: Path) -> None:
    """Rollback (``late_posters`` books beside asks): one silence counted twice, retries halved."""
    source = _SilentFirst(race=False)
    hits = _hits(tmp_path, source)
    calm = threading.Thread(target=hits.offer, args=([_row()],), daemon=True)
    calm.start()
    assert source.entered.wait(_SETTLE)
    hits.urgent([_row()])
    source.opened.set()
    calm.join(_SETTLE)
    source.finished.set()
    assert _until(lambda: not hits._late_names)
    tries = [count for count, _ in hits._again.values()]
    assert tries == [1], f"one silent answer was booked as {tries} unknown misses"
