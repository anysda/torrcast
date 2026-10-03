"""Описатель процесса: поток только при источнике, снятая раздача вне игры до ``add``."""

import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.torrent_file import torrent
from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.adapters.torrserver.describer import DESCRIBER, SETTLE, Describer
from torrcast.adapters.torrserver.torrent_http import TorrentHttp

KEY, DATA = torrent()
LINK = "http://prowlarr.invalid/1/download?link=x"


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


def test_without_a_link_or_a_stored_torrent_no_thread_is_started() -> None:
    assert DESCRIBER.later("http://torrserver", KEY) is None


def test_the_description_reaches_the_service_from_its_own_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LINKS.remember([{"infoHash": KEY.upper(), "downloadUrl": LINK}])
    uploaded: list[tuple[str, bytes]] = []

    def upload(_http: TorrentHttp, key: str, data: bytes) -> bool:
        uploaded.append((key, data))
        return True

    monkeypatch.setattr(TorrentHttp, "fetch", lambda _http, url: DATA if url == LINK else None)
    monkeypatch.setattr(TorrentHttp, "stat", lambda _http, key: 1)
    monkeypatch.setattr(TorrentHttp, "upload", upload)

    thread = DESCRIBER.later("http://torrserver", KEY.upper())
    assert thread is not None
    thread.join(5)

    assert uploaded == [(KEY, DATA)]


def test_a_new_add_after_a_drop_lifts_the_ban() -> None:
    DESCRIBER.closed(KEY)
    assert DESCRIBER.dropped(KEY)

    DESCRIBER.later("http://torrserver", KEY)

    assert not DESCRIBER.dropped(KEY)


def _described(
    monkeypatch: pytest.MonkeyPatch, upload: Callable[[TorrentHttp, str, bytes], bool]
) -> tuple[Describer, FakeClock]:
    LINKS.remember([{"infoHash": KEY.upper(), "downloadUrl": LINK}])
    monkeypatch.setattr(TorrentHttp, "fetch", lambda _http, url: DATA if url == LINK else None)
    monkeypatch.setattr(TorrentHttp, "stat", lambda _http, key: 1)
    monkeypatch.setattr(TorrentHttp, "upload", upload)
    clock = FakeClock(now=10.0)
    return Describer(clock=clock), clock


def test_a_drop_right_after_the_upload_waits_out_the_settle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    describer, clock = _described(monkeypatch, lambda _http, key, data: True)
    thread = describer.later("http://torrserver", KEY)
    assert thread is not None
    thread.join(5)
    clock.now += 0.1

    describer.closed(KEY)

    assert clock.sleeps == [pytest.approx(SETTLE - 0.1)]


def test_a_drop_during_the_upload_returns_only_after_it(monkeypatch: pytest.MonkeyPatch) -> None:
    inside, tick = threading.Event(), threading.Event()
    order: list[str] = []
    describer: Describer

    def upload(_http: TorrentHttp, key: str, data: bytes) -> bool:
        inside.set()
        for _ in range(500):  # подача держится, пока снятие не встало на замок
            if describer.dropped(key):
                break
            tick.wait(0.01)
        order.append("upload done")
        return True

    describer, clock = _described(monkeypatch, upload)
    thread = describer.later("http://torrserver", KEY)
    assert thread is not None
    assert inside.wait(5)

    describer.closed(KEY)
    order.append("dropped")
    thread.join(5)

    assert order == ["upload done", "dropped"]
    assert clock.sleeps == [pytest.approx(SETTLE)]


def test_a_drop_between_the_check_and_the_upload_cancels_the_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded: list[str] = []

    def upload(_http: TorrentHttp, key: str, data: bytes) -> bool:
        uploaded.append(key)
        return True

    describer, clock = _described(monkeypatch, upload)

    def stat(_http: TorrentHttp, key: str) -> int:
        describer.closed(key)  # снятие пришло, когда проверка ``dropped`` уже пройдена
        return 1

    monkeypatch.setattr(TorrentHttp, "stat", stat)
    thread = describer.later("http://torrserver", KEY)
    assert thread is not None
    thread.join(5)

    assert uploaded == []
    assert clock.sleeps == []


def test_a_drop_without_a_description_nearby_does_not_wait() -> None:
    clock = FakeClock()
    Describer(clock=clock).closed(KEY)
    assert clock.sleeps == []
