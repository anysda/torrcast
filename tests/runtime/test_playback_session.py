"""Сборка сеанса показа берёт звенья у модуля команд в момент вызова, а не на импорте."""

from typing import Any

import pytest

from torrcast import commands
from torrcast.adapters.unit_playback_session import UnitPlaybackSession
from torrcast.runtime.playback_session import playback_session


def test_the_session_is_built_from_the_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands, "unit_active", lambda: True)
    monkeypatch.setattr(commands, "unit_key", lambda: "movie:моана-2")

    session = playback_session()

    assert isinstance(session, UnitPlaybackSession)
    assert session.active() is True
    assert session.key() == "movie:моана-2"


def test_a_named_configuration_wins_over_reading_the_file() -> None:
    config: Any = type("Config", (), {"receiver": "mock"})()

    assert playback_session(lambda: config).receiver_name() == "mock"
