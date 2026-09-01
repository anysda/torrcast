"""Шапка пульта собирается из снимка живого показа."""

from types import SimpleNamespace

import pytest

from tgbot.playing_title import playing_title


def test_title_includes_year_and_episode_from_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    class Session:
        def active(self) -> bool:
            return True

        def key(self) -> str:
            return "living"

        def snapshot(self, key: str) -> object:
            assert key == "living"
            return SimpleNamespace(title="Desperate Housewives", year=2004, label="s1e18")

    monkeypatch.setattr("tgbot.playing_title.playback_session", Session)

    assert playing_title() == "Desperate Housewives (2004) s1e18"
