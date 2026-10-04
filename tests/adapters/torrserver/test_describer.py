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
    DESCRIBER.close(KEY, lambda: True)
    assert DESCRIBER.dropped(KEY)

    DESCRIBER.later("http://torrserver", KEY)

    assert not DESCRIBER.dropped(KEY)


class _HeldClock(FakeClock):
    """Сон потока снятия держится, пока тест его не отпустит: видно, кто ждёт."""

    def __init__(self) -> None:
        super().__init__(now=10.0)
        self.release = threading.Event()

    def sleep(self, seconds: float) -> None:
        assert self.release.wait(5)
        super().sleep(seconds)


def _described(
    monkeypatch: pytest.MonkeyPatch, upload: Callable[[TorrentHttp, str, bytes], bool]
) -> tuple[Describer, _HeldClock]:
    LINKS.remember([{"infoHash": KEY.upper(), "downloadUrl": LINK}])
    monkeypatch.setattr(TorrentHttp, "fetch", lambda _http, url: DATA if url == LINK else None)
    monkeypatch.setattr(TorrentHttp, "stat", lambda _http, key: 1)
    monkeypatch.setattr(TorrentHttp, "upload", upload)
    clock = _HeldClock()
    return Describer(clock=clock), clock


def _remover(into: list[str], word: str, flag: threading.Event | None = None) -> Callable[[], bool]:
    def remove() -> bool:
        into.append(word)
        if flag is not None:
            flag.set()
        return True

    return remove


def _described_now(describer: Describer) -> None:
    thread = describer.later("http://torrserver", KEY)
    assert thread is not None
    thread.join(5)


def test_a_drop_right_after_the_upload_waits_out_the_settle_off_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    describer, clock = _described(monkeypatch, lambda _http, key, data: True)
    _described_now(describer)
    clock.now += 0.1
    removed = threading.Event()

    assert describer.close(KEY, _remover([], KEY, removed)) is True
    assert not removed.is_set()  # зовущий вернулся, ``rem`` ждёт своего часа в потоке

    clock.release.set()
    assert removed.wait(5)
    assert clock.sleeps == [pytest.approx(SETTLE - 0.1)]


def test_a_drop_during_the_upload_removes_only_after_it(monkeypatch: pytest.MonkeyPatch) -> None:
    inside, done, removed = threading.Event(), threading.Event(), threading.Event()
    order: list[str] = []

    def upload(_http: TorrentHttp, key: str, data: bytes) -> bool:
        inside.set()
        assert done.wait(5)
        order.append("upload done")
        return True

    describer, clock = _described(monkeypatch, upload)
    clock.release.set()
    thread = describer.later("http://torrserver", KEY)
    assert thread is not None
    assert inside.wait(5)

    assert describer.close(KEY, _remover(order, "removed", removed)) is True
    assert order == []  # подача ещё идёт, а зовущий её не ждал

    done.set()
    thread.join(5)
    assert removed.wait(5)
    assert order == ["upload done", "removed"]
    assert clock.sleeps == [pytest.approx(SETTLE)]


def test_a_second_drop_while_the_first_waits_removes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    describer, clock = _described(monkeypatch, lambda _http, key, data: True)
    _described_now(describer)
    removed: list[str] = []
    first = threading.Event()

    assert describer.close(KEY, _remover(removed, "first", first))
    assert describer.close(KEY, _remover(removed, "second"))
    clock.release.set()

    assert first.wait(5)
    assert removed == ["first"]


def test_a_torrent_added_again_while_the_drop_waits_is_not_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    describer, clock = _described(monkeypatch, lambda _http, key, data: True)
    _described_now(describer)
    removed: list[str] = []
    assert describer.close(KEY, _remover(removed, KEY))
    waiting = [t for t in threading.enumerate() if t.name == f"settle-{KEY}"]

    again = describer.later("http://torrserver", KEY)  # тот же хэш снова нужен показу
    clock.release.set()
    for thread in [*waiting, again]:
        assert thread is not None
        thread.join(5)

    assert len(waiting) == 1
    assert removed == []


def test_a_drop_between_the_check_and_the_upload_cancels_the_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def upload(_http: TorrentHttp, key: str, data: bytes) -> bool:
        calls.append("uploaded")
        return True

    describer, clock = _described(monkeypatch, upload)

    def stat(_http: TorrentHttp, key: str) -> int:
        describer.close(key, _remover(calls, "removed"))  # проверка ``dropped`` уже пройдена
        return 1

    monkeypatch.setattr(TorrentHttp, "stat", stat)
    _described_now(describer)

    assert calls == ["removed"]
    assert clock.sleeps == []


def test_a_drop_without_a_description_nearby_answers_at_once() -> None:
    clock = FakeClock()
    assert Describer(clock=clock).close(KEY, lambda: False) is False
    assert clock.sleeps == []
