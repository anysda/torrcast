"""Сценарий stop останавливает показ и освобождает его раздачу."""

from tests.fakes.console import FakeConsole
from tests.fakes.playback_session import FakePlaybackSession
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
    assert console.messages == ["остановлено: «Луна» на 0:01:05 / 1:00:00"]


def test_stop_reports_empty_session() -> None:
    session = FakePlaybackSession()
    console = FakeConsole()

    Stop(session, console).run()

    assert console.messages == ["ничего не играет"]
