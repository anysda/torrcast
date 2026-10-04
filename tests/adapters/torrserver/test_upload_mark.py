"""Снятие видит подачу описания из другого процесса того же экземпляра (TC-1251).

Два :class:`Describer` над одним каталогом состояния - это страница и показ: у каждого свой
замок, общего у них только диск.
"""

import fcntl
import os
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.torrent_file import torrent
from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.adapters.torrserver import torrent_store
from torrcast.adapters.torrserver.describer import SETTLE, Describer
from torrcast.adapters.torrserver.torrent_http import TorrentHttp
from torrcast.adapters.torrserver.torrent_store import STORE
from torrcast.adapters.torrserver.upload_mark import POLL, UploadMark

KEY, DATA = torrent()
LINK = "http://prowlarr.invalid/2/download?link=y"


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


class _HeldClock(FakeClock):
    """Сон потока снятия держится, пока тест его не отпустит."""

    def __init__(self) -> None:
        super().__init__(now=10.0)
        self.release = threading.Event()

    def sleep(self, seconds: float) -> None:
        assert self.release.wait(5)
        super().sleep(seconds)


def _page(monkeypatch: pytest.MonkeyPatch, upload: Callable[..., bool]) -> _HeldClock:
    LINKS.remember([{"infoHash": KEY.upper(), "downloadUrl": LINK}])
    monkeypatch.setattr(TorrentHttp, "fetch", lambda _http, url: DATA if url == LINK else None)
    monkeypatch.setattr(TorrentHttp, "stat", lambda _http, key: 1)
    monkeypatch.setattr(TorrentHttp, "upload", upload)
    return _HeldClock()


def _remover(into: list[str], flag: threading.Event) -> Callable[[], bool]:
    def remove() -> bool:
        into.append("removed")
        flag.set()
        return True

    return remove


def test_a_drop_from_another_process_right_after_its_upload_waits_out_the_settle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _page(monkeypatch, lambda _http, key, data: True)
    page, show = Describer(clock=clock), Describer(clock=clock)
    thread = page.later("http://torrserver", KEY)
    assert thread is not None
    thread.join(5)
    clock.now += 0.1
    removed: list[str] = []
    done = threading.Event()

    assert show.close(KEY, _remover(removed, done)) is True
    assert removed == []  # ``rem`` не ушёл в те миллисекунды, что роняют службу

    clock.release.set()
    assert done.wait(5)
    assert clock.sleeps == [pytest.approx(SETTLE - 0.1)]


def test_a_drop_from_another_process_during_its_upload_removes_only_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inside, finish, done = threading.Event(), threading.Event(), threading.Event()
    order: list[str] = []

    def upload(_http: TorrentHttp, key: str, data: bytes) -> bool:
        inside.set()
        assert finish.wait(5)
        order.append("upload done")
        return True

    clock = _page(monkeypatch, upload)
    page, show = Describer(clock=clock), Describer(clock=clock)
    thread = page.later("http://torrserver", KEY)
    assert thread is not None
    assert inside.wait(5)

    assert show.close(KEY, _remover(order, done)) is True
    finish.set()
    thread.join(5)
    assert order == ["upload done"]  # снятие ждало чужую подачу, хотя своего замка у неё нет
    clock.release.set()  # сон держался, пока шла подача: часы подделки не убежали за выдержку

    assert done.wait(5)
    assert order == ["upload done", "removed"]
    # Не больше одного опроса замка после подачи; выдержка после её конца была.
    settle = [s for s in clock.sleeps if s != POLL]
    assert len(settle) == 1
    assert 0 < settle[0] <= SETTLE


def test_an_old_upload_from_another_process_does_not_delay_the_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _page(monkeypatch, lambda _http, key, data: True)
    page, show = Describer(clock=clock), Describer(clock=clock)
    thread = page.later("http://torrserver", KEY)
    assert thread is not None
    thread.join(5)
    clock.now += SETTLE + 1.0

    assert show.close(KEY, lambda: False) is False
    assert clock.sleeps == []


def test_an_upload_that_never_lets_go_still_gets_a_full_settle() -> None:
    clock = FakeClock()
    mark = UploadMark(STORE.folder, clock)
    with mark.delivering(KEY):
        assert mark.left(KEY, SETTLE, timeout=0.2) == SETTLE
    assert clock.sleeps and set(clock.sleeps) == {POLL}


def test_the_mark_leaves_together_with_its_trimmed_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torrent_store, "CAP", 1)
    other = "f" * 40
    STORE.store(KEY, DATA)
    with UploadMark(STORE.folder, FakeClock()).delivering(KEY) as stamp:
        stamp()
    marked = STORE.folder() / UploadMark.name(KEY)
    assert marked.is_file()
    os.utime(STORE.folder() / f"{KEY}.torrent", (1.0, 1.0))  # старше нового описания

    STORE.store(other, DATA)

    assert not marked.exists()
    assert STORE.has(other)


def test_a_mark_is_free_once_the_upload_is_over() -> None:
    mark = UploadMark(STORE.folder, FakeClock())
    with mark.delivering(KEY):
        pass
    fd = os.open(STORE.folder() / UploadMark.name(KEY), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # замок подачи отпущен
    finally:
        os.close(fd)
