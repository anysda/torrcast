"""The history waits out a short source quiet instead of answering without covers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

import hass.quiet_wait
from hass.hit_posters import FIELD
from tests.test_hit_claims import _Clock, _posters, _Storm
from tests.test_hit_posters import FakeSource, _row
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue


def _calm_after(
    clock: _Clock, storm: _Storm, source: FakeSource, pages: dict[str, list[str]]
) -> Callable[[float], None]:
    def pause(seconds: float) -> None:
        clock.now += seconds
        storm.troubled = False
        source.pages = pages

    return pause


def test_a_history_cover_deferred_by_a_429_is_named_after_the_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback (``offer`` answers ``ahead`` at once): the history goes out without a cover."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(calm=105.0)
    monkeypatch.setattr(
        hass.quiet_wait, "_pause", _calm_after(clock, storm, source, {"Тачки": ["Cars"]})
    )
    rows: list[JsonValue] = [_row()]

    said = _posters(tmp_path, source, clock, storm).offer(rows, ahead=True)

    assert len(source.judged) == 2, "the quiet ended within the bound and nobody asked again"
    assert clock.now == 105.0, "the history slept past the end of the quiet"
    assert isinstance(said[0], dict) and FIELD in said[0]


def test_a_long_quiet_does_not_hold_the_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A quiet longer than the bound: the history answers at once, the shelf asks later."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(calm=160.0)
    monkeypatch.setattr(hass.quiet_wait, "_pause", _calm_after(clock, storm, source, {}))

    said = _posters(tmp_path, source, clock, storm).offer([_row()], ahead=True)

    assert len(source.judged) == 1 and clock.now == 100.0
    assert isinstance(said[0], dict) and FIELD not in said[0]


def test_the_visible_row_does_not_wait_for_the_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the history waits: a search row answers at once and the quiet stays with it."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(calm=105.0)
    monkeypatch.setattr(hass.quiet_wait, "_pause", _calm_after(clock, storm, source, {}))

    _posters(tmp_path, source, clock, storm).offer([_row()], urgent=True)

    assert clock.now == 100.0


class _Half(FakeSource):
    """One picture has a cover, the other stays silent under the same storm."""

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        said = super().wanted(asks, timeout)
        return {ask: urls for ask, urls in said.items() if urls}


def test_a_history_with_a_cover_does_not_wait_for_the_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback (any deferred picture holds the answer): 5 s more for no new cover."""
    source, clock, storm = _Half(pages={"Тачки": ["Cars"]}), _Clock(), _Storm(calm=105.0)
    monkeypatch.setattr(hass.quiet_wait, "_pause", _calm_after(clock, storm, source, {}))
    rows: list[JsonValue] = [_row(), _row("Нет такой")]

    said = _posters(tmp_path, source, clock, storm).offer(rows, ahead=True)

    assert clock.now == 100.0, "a history with a cover waited out the quiet"
    assert source.calls == 1, "a history with a cover asked its misses again"
    assert isinstance(said[0], dict) and FIELD in said[0]
