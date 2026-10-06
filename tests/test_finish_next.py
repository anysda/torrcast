"""Зеркало штатного завершения серии без второго запуска."""

from __future__ import annotations

from pathlib import Path

import pytest

import hass.finish_next as next_module
from hass.finish_next import finish_next
from hass.motion import Motion
from hass.say import SEEKBY
from tests.fakes.playback_session import FakePlaybackSession
from torrcast.domain.config import Config
from torrcast.domain.playback_snapshot import PlaybackSnapshot


def test_the_next_episode_seeks_only_the_remainder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Каста нет: остаток считается по снимку моста, до секунды перед концом."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    session = FakePlaybackSession(
        playing=True,
        play_key="tv:show",
        shown=PlaybackSnapshot(key="tv:show", title="Show", position=600.0, duration=1800.0),
    )
    controlled: list[tuple[str, float]] = []
    monkeypatch.setattr(next_module, "next_show", lambda *_: True)
    monkeypatch.setattr(next_module, "tab_finish", lambda *_: False)

    finish_next(
        session, {}, Config, lambda command, arg: controlled.append((command, arg)), Motion()
    )

    assert controlled == [(SEEKBY, 1199.0)]
