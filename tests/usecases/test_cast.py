"""Проверяет сценарий показа на фейковых движке и приёмнике."""

from tests.fakes.receiver import FakeReceiver
from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain.position import Position
from torrcast.usecases.cast import Cast


def test_cast_passes_stream_to_receiver() -> None:
    torrents = FakeTorrentEngine(torrent_hash="abc")
    receiver = FakeReceiver(Position(0.0, 0.0))

    torrent_hash = Cast(torrents, receiver).run("magnet:?xt=film", 3, "Фильм", 12.5)

    assert torrent_hash == "abc"
    assert torrents.added == ["magnet:?xt=film"]
    assert torrents.stream_requests == [("abc", 3)]
    assert receiver.plays == [("http://fake/abc/3", "Фильм", 12.5)]
