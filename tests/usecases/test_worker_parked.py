"""Раздача, которую продолжит закладка, переживает показ и уходит со следующим запуском."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes import composition
from tests.usecases.test_worker import KEY, _dropped, _own_show, _played
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.state import State
from torrcast.cli.play import play
from torrcast.domain.args import Args
from torrcast.domain.continue_row import WARM_ROW
from torrcast.domain.entry import Entry
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.torrent_claims import CLAIMS
from torrcast.usecases.torrents import _release_parked
from torrcast.usecases.worker import _cmd_worker

__all__ = ["_own_show"]  # фикстура юнита показа: запись «Брата» и подделки службы


def _stopped(
    config: Any, source: str, audio: int, about: str, clock: Any, watch: Any, **_rest: Any
) -> int:
    """«Завершить» на середине фильма: закладка продолжит его с места."""
    watch.see(watch.entry.dur / 2)
    watch.close()
    return 0


def _entry() -> Any:
    return State.load().get(KEY)


def test_a_show_stopped_midway_leaves_its_release_to_the_bookmark() -> None:
    """«Рататуй»: снесённая концом показа раздача заново читала метаданные 4.4 с."""
    assert _cmd_worker(KEY, play=_stopped) == 0

    assert _dropped == []
    assert (_entry().torrent, _entry().parked) == ("", "hash"), "живым показом она не считается"


def test_a_finished_show_takes_its_release_and_the_parked_one_away() -> None:
    state = State.load()
    state.entries[KEY].parked = "old"
    state.save()

    assert _cmd_worker(KEY, play=_played) == 0

    assert sorted(_dropped) == ["hash", "old"]
    assert (_entry().torrent, _entry().parked) == ("", "")


class _Service:
    def __init__(self) -> None:
        self.dropped: list[str] = []

    def __call__(self, url: str, timeout: float = 30.0) -> _Service:
        return self

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)
        return True


def _park(fresher: int) -> None:
    """Закладка «Брата» с оставленной раздачей и ``fresher`` записей ряда свежее неё."""
    state = State.load()
    state.entries[KEY].parked = "hash"
    state.entries[KEY].updated = "2026-09-01T00:00:00+00:00"
    for n in range(fresher):
        state.entries[f"movie:{n}:2000"] = Entry(
            title=str(n), magnet=f"magnet:?xt={n}", updated=f"2026-09-2{n}T00:00:00+00:00"
        )
    state.save()


def test_a_started_show_takes_a_parked_release_the_page_does_not_hold(
    show_unit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _park(fresher=WARM_ROW)
    service = _Service()
    composition.use_engines(monkeypatch, service)
    show_unit.alive = False
    page = _Service()  # держатель страницы: CLAIMS помнит его слабой ссылкой
    CLAIMS.claim("hash", page)
    try:
        _release_parked(load_config())
    finally:
        CLAIMS.unclaim("hash", page)
    assert (service.dropped, _entry().parked) == ([], "hash"), "страница держит - не трогать"

    _release_parked(load_config())

    assert (service.dropped, _entry().parked) == (["hash"], ""), "выпала из первых - снос"


def _start(show_unit: Any, service: _Service) -> list[str]:
    """«Продолжить» «Брата» до картинки; ответ - что служба успела снести к подъёму."""
    seen: list[str] = []

    def resume(*_args: object, **_rest: object) -> int:
        seen.extend(service.dropped)
        show_unit.alive = True  # показ поднят
        return 0

    def never(*_args: object, **_rest: object) -> int:
        return pytest.fail("до поиска доходить нечему")

    def command(args: Args) -> int:
        return _cmd_play(args, resume=resume, choose=never)

    assert play(Args(query=["брат"]), command) == 0
    return seen


def test_a_click_does_not_wait_for_a_parked_release(
    show_unit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Снос раздачи закладки в пути клика ждал общий замок службы до 3.0 с."""
    _park(fresher=WARM_ROW)
    service = _Service()
    composition.use_engines(monkeypatch, service)
    show_unit.alive = False

    assert _start(show_unit, service) == []


def test_a_parked_release_still_goes_once_the_show_is_up(
    show_unit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _park(fresher=WARM_ROW)
    service = _Service()
    composition.use_engines(monkeypatch, service)
    show_unit.alive = False

    _start(show_unit, service)

    assert (service.dropped, _entry().parked) == (["hash"], ""), "сирота не копится"


def test_a_parked_release_of_the_first_resumes_keeps_its_disk_cache(
    show_unit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«Интерстеллар»: снос стирал кэш закладки, и «Продолжить» тянуло её из роя 36 с."""
    _park(fresher=WARM_ROW - 1)
    service = _Service()
    composition.use_engines(monkeypatch, service)
    show_unit.alive = False

    _release_parked(load_config())

    assert (service.dropped, _entry().parked) == ([], "hash")


def test_stop_leaves_the_release_the_unit_parked() -> None:
    """«Завершить» сносил раздачу ещё раз после юнита, и закладка снова ждала метаданные."""
    from torrcast.adapters.unit_playback_session import _left

    torrent_hash = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"
    entry = Entry(title="Брат", magnet=f"magnet:?xt=urn:btih:{torrent_hash}")

    assert _left(entry) == torrent_hash, "юнит не оставил её никому - сносится как прежде"
    entry.parked = torrent_hash
    assert _left(entry) == ""


def test_a_parked_release_the_risen_show_holds_stays(
    show_unit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Снос идёт уже при живом показе: его раздачу из-под экрана не выдёргивать."""
    _park(fresher=WARM_ROW)
    state = State.load()
    state.entries["movie:0:2000"].torrent = "hash"
    state.save()
    service = _Service()
    composition.use_engines(monkeypatch, service)

    _release_parked(load_config())

    assert (service.dropped, _entry().parked) == ([], "hash")
