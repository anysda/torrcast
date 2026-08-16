"""Проверяет ожидание метаданных TorrServer через фейковые часы."""

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.torr_server import TorrServer


class _Ready(TorrServer):
    def __init__(self, clock: FakeClock) -> None:
        super().__init__("http://torrserver", clock=clock)
        self.calls = 0

    def status(self, torrent_hash: str) -> dict[str, object]:
        self.calls += 1
        if self.calls < 3:
            return {}
        return {"file_stats": [{"id": 2, "path": "film.mkv", "length": 10}]}


def test_ожидание_метаданных_берёт_время_из_порта() -> None:
    clock = FakeClock()
    files = _Ready(clock).wait_files("hash", timeout=1.0)
    assert files[0].name == "film.mkv"
    assert clock.sleeps == [0.05, 0.07500000000000001]
