"""Checks how the client fetches Wikimedia image files: two at once, and quiet after a 429."""

import threading
import time

import pytest

from torrcast.adapters.wiki import http_json_client
from torrcast.adapters.wiki.http_json_client import IMAGE_LANES, HttpJsonClient

_FILE = "https://upload.wikimedia.org/wikipedia/ru/a/ab/Poster.jpg"


class _Files:
    """A fake files server: counts requests in flight and answers the given statuses."""

    def __init__(self, statuses: list[int], hold: float = 0.0) -> None:
        self.statuses = statuses
        self.hold = hold
        self.asked = 0
        self.inflight = 0
        self.most = 0
        self.lock = threading.Lock()

    def connection(self, host: str, **_kwargs: object) -> object:
        files = self

        class _Reply:
            def __init__(self) -> None:
                with files.lock:
                    self.status = files.statuses.pop(0) if files.statuses else 200

            def getheader(self, name: str) -> str | None:
                return "11" if name == "Retry-After" else None

            def read(self, _limit: int = 0) -> bytes:
                return b"picture"

        class _Connection:
            def request(self, *_args: object, **_kwargs: object) -> None:
                with files.lock:
                    files.asked += 1
                    files.inflight += 1
                    files.most = max(files.most, files.inflight)
                time.sleep(files.hold)

            def getresponse(self) -> _Reply:
                return _Reply()

            def close(self) -> None:
                with files.lock:
                    files.inflight -= 1

        return _Connection()


@pytest.mark.machine
def test_no_more_than_two_images_are_fetched_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eight shelf posters asked together reach the files server two at a time."""
    files = _Files([], hold=0.05)
    monkeypatch.setattr(http_json_client, "_IPv4Connection", files.connection)
    client = HttpJsonClient("torrcast/test")
    wave = [threading.Thread(target=client.fetch, args=(_FILE, 5.0)) for _ in range(8)]
    for thread in wave:
        thread.start()
    for thread in wave:
        thread.join(5.0)
    assert files.asked == 8
    assert files.most == IMAGE_LANES == 2


def test_a_429_of_the_files_server_quiets_the_next_images(monkeypatch: pytest.MonkeyPatch) -> None:
    """After a 429 with ``Retry-After`` the next image is refused locally, not asked again."""
    files = _Files([429, 200])
    monkeypatch.setattr(http_json_client, "_IPv4Connection", files.connection)
    client = HttpJsonClient("torrcast/test")
    start = time.monotonic()
    with pytest.raises(OSError, match="429"):
        client.fetch(_FILE, 0.5)
    with pytest.raises(OSError, match="image lane"):
        client.fetch(_FILE, 0.5, urgent=True)
    assert files.asked == 1
    assert client.troubled_since(start)
    assert client.calm_at() >= start + 11.0
