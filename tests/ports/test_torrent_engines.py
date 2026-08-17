"""Проверяет контракт завода службы раздач и поведение его фейка."""

from tests.fakes.torrent_engines import FakeTorrentEngines
from torrcast.ports.torrent_engines import TorrentEngines


def test_the_address_reaches_the_factory() -> None:
    factory = FakeTorrentEngines()
    port: TorrentEngines = factory
    engine = port("http://service:8090")
    assert engine.add("magnet") == "hash"
    assert factory.asked == [("http://service:8090", 30.0)]


def test_a_short_deadline_is_not_the_same_question_as_the_usual_one() -> None:
    """Сторож спрашивает службу коротким сроком, показ - обычным: срок едет в завод."""
    factory = FakeTorrentEngines()
    port: TorrentEngines = factory
    port("http://service:8090", timeout=3.0)
    port("http://service:8090")
    assert factory.asked == [("http://service:8090", 3.0), ("http://service:8090", 30.0)]
