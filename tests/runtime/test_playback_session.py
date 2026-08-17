"""Сборка сеанса показа: звенья из их настоящих домов, а юнит - с порта."""

from typing import Any

from tests.fakes.show_unit import FakeShowUnit
from torrcast.adapters.unit_playback_session import UnitPlaybackSession
from torrcast.runtime.playback_session import playback_session


def test_the_session_asks_the_unit_that_the_root_installed(show_unit: FakeShowUnit) -> None:
    """Живость и ключ показа сеанс спрашивает у назначенного юнита, а не у systemd."""
    show_unit.alive = True
    show_unit.playing = "movie:моана-2"

    session = playback_session()

    assert isinstance(session, UnitPlaybackSession)
    assert session.active() is True
    assert session.key() == "movie:моана-2"


def test_a_named_configuration_wins_over_reading_the_file() -> None:
    config: Any = type("Config", (), {"receiver": "mock"})()

    assert playback_session(lambda: config).receiver_name() == "mock"
