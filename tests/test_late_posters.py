"""Mirror for :mod:`hass.late_posters`: a quick miss still finishes its trusted source."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from hass.hit_ask import _about, _name
from hass.hit_posters import FIELD, HitPosters
from hass.late_posters import Land
from hass.poster_shelf import PosterShelf
from tests.test_hit_posters import _SETTLE, FakeSource, _hits, _named, _row
from torrcast.domain.facts.ask import Ask


def _until(ready: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + _SETTLE
    while not ready() and time.monotonic() < deadline:
        threading.Event().wait(0.02)
    return ready()


def test_an_urgent_silence_keeps_waiting_for_its_race(tmp_path: Path) -> None:
    """A source still on the wire at the race deadline is not proof that there is no poster."""
    gate = threading.Event()

    class LateSource(FakeSource):
        def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
            return {}

        def finish_urgent(
            self, asks: Sequence[Ask], timeout: float, land: Land
        ) -> dict[Ask, list[str]]:
            gate.wait(_SETTLE)
            land({ask: ["later"] for ask in asks})
            return {ask: ["later"] for ask in asks}

    hits, row = _hits(tmp_path, LateSource()), _row()
    first = hits.urgent([row])[0]
    assert isinstance(first, dict) and FIELD not in first
    gate.set()
    assert _until(lambda: hits.landed(row))


def test_a_race_that_never_answered_is_asked_again_not_held_as_a_miss(tmp_path: Path) -> None:
    """🔴 A race that ends in silence leaves the picture unknown: the next list asks again."""

    class DeafSource(FakeSource):
        deaf: bool = True

        def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
            return {} if self.deaf else super().wanted(asks, timeout)

        def finish_urgent(
            self, asks: Sequence[Ask], timeout: float, land: Land
        ) -> dict[Ask, list[str]]:
            return {}

    source = DeafSource()
    hits, row = _hits(tmp_path, source, now=lambda: 0.0), _row()
    first = hits.urgent([row])[0]
    assert isinstance(first, dict) and FIELD not in first
    ask = _about(row)
    assert ask is not None
    assert _until(lambda: _name(ask) not in hits._late_names)
    source.deaf = False
    assert isinstance(_named(hits, row), str)


class _BackgroundRefused:
    """Only a background request was turned away: the visible row's race saw no refusal."""

    def troubled_since(self, moment: float, urgent: bool = False) -> bool:
        return not urgent

    def calm_at(self) -> float:
        return 0.0


def test_a_race_answered_empty_beside_a_background_refusal_is_a_miss(tmp_path: Path) -> None:
    """A refused card extract made this miss unknown, and the row re-asked it until 37 s."""

    class EmptySource(FakeSource):
        def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
            return {}

        def finish_urgent(
            self, asks: Sequence[Ask], timeout: float, land: Land
        ) -> dict[Ask, list[str]]:
            return {ask: [] for ask in asks}

    shelf = PosterShelf(home=lambda: tmp_path)
    hits = HitPosters(EmptySource(), shelf, lambda: 0.0, _BackgroundRefused())
    row = _row()
    ask = _about(row)
    assert ask is not None
    hits.urgent([row])
    assert _until(lambda: _name(ask) not in hits._late_names)
    assert not hits.due([row]), "an answered race is asked again as if it were silent"
