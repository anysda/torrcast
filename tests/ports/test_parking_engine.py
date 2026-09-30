"""Служба раздач паркует раздачу только там, где умеет не стирать кэш."""

from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.ports.parking_engine import ParkingEngine


def test_torrserver_parks_and_the_bare_engine_does_not() -> None:
    """Держатель выбирает закрытие по договору: подделка без ``park`` сносит, как прежде."""
    assert isinstance(TorrServer("http://torrserver"), ParkingEngine)
    assert not isinstance(FakeTorrentEngine(), ParkingEngine)
