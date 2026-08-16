"""Проверяет контракт каталога торрентов и поведение его фейка."""

from tests.fakes.torrent_index import FakeTorrentIndex
from torrcast.domain.release import Release
from torrcast.ports.torrent_index import TorrentIndex


def test_fake_records_search_and_returns_results() -> None:
    release = Release("raw", "Title")
    fake = FakeTorrentIndex([release])
    port: TorrentIndex = fake
    assert port.search("query") == [release]
    assert fake.queries == ["query"]
