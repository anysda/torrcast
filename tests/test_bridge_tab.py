"""Мост отдаёт ключ вкладки следующей серии: ``/api/next`` не глушит ``--tab``."""

from __future__ import annotations

import pytest

from tests.fakes.playback_session import FakePlaybackSession
from tests.test_bridge import _bridge
from torrcast.domain.json_value import JsonValue


def test_the_next_episode_is_handed_the_tab_that_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Следующая серия вкладки решает профиль по её ключу (:func:`hass.next_show.next_show`)."""
    tabs: list[str] = []

    def next_show(session: object, body: dict[str, JsonValue], tab: str = "") -> None:
        tabs.append(tab)

    monkeypatch.setattr("hass.bridge.next_show", next_show)
    bridge = _bridge(FakePlaybackSession(playing=True, play_key="tv:шоу"))

    bridge.next({}, "gecko-linux")

    assert tabs == ["gecko-linux"]
