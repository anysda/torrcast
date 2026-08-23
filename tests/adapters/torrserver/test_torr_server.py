"""Проверяет ожидание метаданных TorrServer через фейковые часы."""

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.torr_server import TorrServer


class _Recording(TorrServer):
    def __init__(self) -> None:
        super().__init__("http://torrserver")
        self.body: dict[str, object] = {}

    def _post(self, path: str, body: dict[str, object], json_body: bool = True) -> dict[str, str]:
        self.body = body
        return {"hash": "abc"}


def test_an_added_torrent_is_saved_so_its_disk_cache_survives_a_restart() -> None:
    server = _Recording()

    assert server.add("magnet:?xt=urn:btih:abc") == "abc"

    assert server.body["save_to_db"] is True


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
