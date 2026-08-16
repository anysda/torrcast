"""Сценарий status описывает живой и завершённый показ."""

from tests.fakes.clock import FakeClock
from tests.fakes.console import FakeConsole
from tests.fakes.playback_session import FakePlaybackSession
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.usecases.status import Status


def test_status_prints_playing_snapshot() -> None:
    session = FakePlaybackSession(
        playing=True,
        play_key="moon",
        shown=PlaybackSnapshot("moon", "Луна", 65, 3600, quality="1080p", file_index=2),
    )
    console = FakeConsole()

    assert Status(session, console, FakeClock()).run() == 0
    assert console.messages[0] == "играю «Луна» · 1080p - 0:01:05 / 1:00:00"
    assert console.messages[-1].startswith("   moon · файл #2 · дорожка 1")


def test_status_prints_last_resumable_snapshot() -> None:
    session = FakePlaybackSession(shown=PlaybackSnapshot("moon", "Луна", 65, 3600))
    console = FakeConsole()

    Status(session, console, FakeClock()).run()

    assert console.messages == [
        "ничего не играет",
        "последнее: «Луна» на 0:01:05 / 1:00:00",
    ]
