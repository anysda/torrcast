"""Сценарий stop останавливает показ и освобождает его раздачу."""

from tests.fakes.console import FakeConsole
from tests.fakes.playback_session import FakePlaybackSession
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.usecases.stop import Stop


def test_stop_reports_played_title_and_releases_torrent() -> None:
    session = FakePlaybackSession(
        playing=True,
        play_key="movie",
        shown=PlaybackSnapshot("movie", "Луна", 65, 3600, torrent_hash="abc"),
    )
    console = FakeConsole()

    assert Stop(session, console).run() == 0
    assert session.stopped == 1
    assert session.released == ["abc"]
    said = phrase("stop.stopped", title="Луна", pos="0:01:05", duration="1:00:00")
    assert console.messages == [said]


def test_stop_reports_empty_session() -> None:
    session = FakePlaybackSession()
    console = FakeConsole()

    Stop(session, console).run()

    assert console.messages == [phrase("stop.nothing_playing")]


def test_stop_names_the_picture_by_its_original_under_english(_english: None) -> None:
    """Под EN stopped зовёт картину тем же именем, что строка запуска показа."""
    session = FakePlaybackSession(
        playing=True,
        play_key="movie",
        shown=PlaybackSnapshot("movie", "Ванпанчмен", 65, 3600, original="One Punch Man"),
    )
    console = FakeConsole()

    assert Stop(session, console).run() == 0
    assert console.messages == [
        phrase("stop.stopped", title="One Punch Man", pos="0:01:05", duration="1:00:00")
    ]
