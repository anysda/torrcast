"""Сценарий status описывает живой и завершённый показ."""

from tests.fakes.clock import FakeClock
from tests.fakes.console import FakeConsole
from tests.fakes.playback_session import FakePlaybackSession
from torrcast.domain.catalogs.phrase import phrase
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
    assert console.messages[0] == phrase(
        "status.playing", what="«Луна» · 1080p", pos="0:01:05", duration="1:00:00"
    )
    assert console.messages[-1] == phrase(
        "status.file_info",
        ident="moon",
        file=2,
        track=1,
        addr=session.stream_address(),
        receiver=session.receiver_name(),
    )


def test_status_prints_last_resumable_snapshot() -> None:
    session = FakePlaybackSession(shown=PlaybackSnapshot("moon", "Луна", 65, 3600))
    console = FakeConsole()

    Status(session, console, FakeClock()).run()

    assert console.messages == [
        phrase("status.nothing_playing"),
        phrase("status.last_resumable", title="Луна", pos="0:01:05", duration="1:00:00"),
    ]


def test_status_names_the_picture_by_its_original_under_english(_english: None) -> None:
    """Под EN status зовёт картину тем же именем, что строка запуска показа."""
    session = FakePlaybackSession(
        playing=True,
        play_key="moon",
        shown=PlaybackSnapshot("moon", "Ванпанчмен", 65, 3600, original="One Punch Man"),
    )
    console = FakeConsole()

    Status(session, console, FakeClock()).run()

    assert console.messages[0] == phrase(
        "status.playing", what="«One Punch Man»", pos="0:01:05", duration="1:00:00"
    )
