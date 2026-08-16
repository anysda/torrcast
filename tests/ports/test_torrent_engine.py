"""Проверяет контракт движка торрентов и поведение его фейка."""

from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.torrent_engine import TorrentEngine


def test_fake_records_torrent_operations() -> None:
    fake = FakeTorrentEngine("abc", [TorrFile(2, "film.mkv")])
    port: TorrentEngine = fake
    assert port.add("magnet") == "abc"
    assert port.files("abc") == [TorrFile(2, "film.mkv")]
    assert port.stream_url("abc", 2) == "http://fake/abc/2"
    assert port.remove("abc")
    assert (fake.added, fake.stream_requests, fake.removed) == (["magnet"], [("abc", 2)], ["abc"])
