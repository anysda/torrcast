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
    assert port.drop("abc")
    assert (fake.added, fake.stream_requests, fake.dropped) == (["magnet"], [("abc", 2)], ["abc"])


def test_metadata_wait_carries_the_timeout_and_the_grace() -> None:
    """Оба срока доезжают до службы: свой у метаданных и свой у приговора «рой пуст»."""
    fake = FakeTorrentEngine("abc", [TorrFile(1, "s01e01.mkv")])
    port: TorrentEngine = fake
    assert port.wait_files("abc", timeout=12.0, grace=4.0) == [TorrFile(1, "s01e01.mkv")]
    assert fake.awaited == [("abc", 12.0, 4.0)]


def test_a_silent_service_reports_a_failed_removal_instead_of_raising() -> None:
    """Снос отвечает «не убрал», а не исключением: уборка идёт на выходе и не вправе падать."""
    fake = FakeTorrentEngine(silent=True)
    port: TorrentEngine = fake
    assert port.drop("abc") is False
    assert fake.dropped == ["abc"]


def test_cache_counters_come_through_as_the_service_gave_them() -> None:
    fake = FakeTorrentEngine(cached={"Filled": 512})
    port: TorrentEngine = fake
    assert port.cache("abc") == {"Filled": 512}
