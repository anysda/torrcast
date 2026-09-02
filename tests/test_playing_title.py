"""Шапка пульта собирается из снимка живого показа."""

import pytest

from tgbot.playing_title import playing_title
from torrcast.domain.playback_snapshot import PlaybackSnapshot


def test_title_includes_year_and_episode_from_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    class Session:
        def active(self) -> bool:
            return True

        def key(self) -> str:
            return "living"

        def snapshot(self, key: str) -> object:
            assert key == "living"
            return PlaybackSnapshot("living", "Desperate Housewives", year=2004, label="s1e18")

    monkeypatch.setattr("tgbot.playing_title.playback_session", Session)

    assert playing_title() == "Desperate Housewives (2004) s1e18"


def test_inactive_show_does_not_fall_back_to_the_last_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Session:
        def active(self) -> bool:
            return False

        def key(self) -> str:
            raise AssertionError("у мёртвого юнита ключ не спрашивают")

        def snapshot(self, _key: str) -> object:
            raise AssertionError("последний сохранённый показ не является живым")

    monkeypatch.setattr("tgbot.playing_title.playback_session", Session)

    assert playing_title() == ""
