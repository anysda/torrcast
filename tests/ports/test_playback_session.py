"""Порт сеанса объединяет операции stop и status."""

from torrcast.ports.playback_session import PlaybackSession


def test_playback_session_is_protocol() -> None:
    assert PlaybackSession.__name__ == "PlaybackSession"
