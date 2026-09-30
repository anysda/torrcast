"""Mirror for the visible row judging beside a calm verdict (:data:`hass.hit_claims._BESIDE`).

The history, shelves and «related» build their verdicts through the slow calm source, 8-14 s
for a batch on a cold stand. The search row asking about the same picture meanwhile judged
nothing and waited for them, so its covers came seconds after the row itself.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from hass.hit_posters import FIELD, HitPosters
from hass.late_posters import Land
from tests.test_hit_posters import _SETTLE, FakeSource, _hits, _row
from tests.test_late_posters import _until
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue


class _TwoPaths(FakeSource):
    """The first verdict (the calm path) stands until the probe opens it; the rest are quick.

    ``race`` - whether the visible row's quick race names the picture; ``late`` - whether the
    source still in flight at its deadline lands it afterwards.
    """

    def __init__(self, race: bool = True, late: bool = False) -> None:
        super().__init__()
        self.race, self.late, self.first = race, late, True
        self.entered, self.opened, self.finished = (threading.Event() for _ in range(3))

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        if self.first:
            self.first = False
            self.entered.set()
            self.opened.wait(_SETTLE)
            return super().wanted(asks, timeout)
        if self.race:
            return super().wanted(asks, timeout)
        self.judged.extend(asks)
        return {}

    def finish_urgent(
        self, asks: Sequence[Ask], timeout: float, land: Land
    ) -> dict[Ask, list[str]]:
        self.finished.wait(_SETTLE)
        if not self.late:
            return {}
        land({ask: ["Cars"] for ask in asks})
        return {ask: ["Cars"] for ask in asks}


def _calm_first(tmp_path: Path, source: _TwoPaths) -> tuple[HitPosters, threading.Thread]:
    hits = _hits(tmp_path, source)
    calm = threading.Thread(target=hits.offer, args=([_row()],), daemon=True)
    calm.start()
    assert source.entered.wait(_SETTLE)
    return hits, calm


@pytest.mark.machine
def test_the_visible_row_does_not_wait_for_a_calm_verdict(tmp_path: Path) -> None:
    """Rollback (``_known`` answers claimed): the row waits out the calm path and shows no name."""
    source = _TwoPaths()
    hits, calm = _calm_first(tmp_path, source)
    began = time.monotonic()
    shown = hits.urgent([_row()])[0]
    took = time.monotonic() - began
    source.opened.set()
    calm.join(_SETTLE)
    assert took < 1.0, f"the visible row waited {took:.1f} s for the calm verdict"
    assert isinstance(shown, dict) and FIELD in shown


@pytest.mark.machine
def test_two_verdicts_of_one_picture_fetch_its_bytes_once(tmp_path: Path) -> None:
    """Rollback (``hit_book`` without the carried check): the calm answer loads the bytes again."""
    source = _TwoPaths()
    hits, calm = _calm_first(tmp_path, source)
    hits.urgent([_row()])
    assert _until(lambda: hits.landed(_row()))
    source.opened.set()
    calm.join(_SETTLE)
    threading.Event().wait(0.2)
    assert len(source.loaded) == 1, "the picture's bytes travelled twice"


@pytest.mark.machine
def test_a_silent_late_race_does_not_undo_a_landed_picture(tmp_path: Path) -> None:
    """Rollback (``_missed`` without the landed check): the page waits on a landed cover."""
    source = _TwoPaths(race=False)
    hits, calm = _calm_first(tmp_path, source)
    hits.urgent([_row()])
    source.opened.set()
    calm.join(_SETTLE)
    assert _until(lambda: hits.landed(_row()))
    source.finished.set()
    assert _until(lambda: not hits._late_names)
    assert not hits.pending([_row()]), "a silent race re-opened a picture already landed"


@pytest.mark.machine
def test_a_late_answer_for_a_landed_picture_fetches_nothing(tmp_path: Path) -> None:
    """Rollback (``late_posters.land`` without the carried check): the late answer loads again."""
    source = _TwoPaths(race=False, late=True)
    hits, calm = _calm_first(tmp_path, source)
    hits.urgent([_row()])
    source.opened.set()
    calm.join(_SETTLE)
    assert _until(lambda: hits.landed(_row()))
    source.finished.set()
    assert _until(lambda: not hits._late_names)
    threading.Event().wait(0.2)
    assert len(source.loaded) == 1, "the late answer fetched the landed picture again"


@pytest.mark.machine
def test_a_growing_row_asks_the_source_beside_a_calm_claim_once(tmp_path: Path) -> None:
    """Rollback (every show judges beside): a row growing to five lines raced the source 5 times.

    Each race was IMDb plus Wikipedia (429 on a cold stand) and one more late-landing thread.
    """
    source = _TwoPaths(race=False)
    hits, calm = _calm_first(tmp_path, source)
    rows: list[JsonValue] = [_row(), *(_row(f"Film {n}", 2000 + n) for n in range(4))]
    for shown in range(1, len(rows) + 1):
        began = time.monotonic()
        hits.urgent(rows[:shown])
        assert time.monotonic() - began < 1.0, "the row waited for the calm verdict"
    asked = sum(ask.title == "Тачки" for ask in source.judged)
    source.opened.set()
    source.finished.set()
    calm.join(_SETTLE)
    assert asked == 1, f"the source was asked beside the calm claim {asked} times"
