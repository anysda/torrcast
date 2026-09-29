"""Раздача, которую продолжит закладка, переживает показ и уходит со следующим запуском."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes import composition
from tests.usecases.test_worker import KEY, _dropped, _own_show, _played
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.state import State
from torrcast.usecases.torrent_claims import CLAIMS
from torrcast.usecases.torrents import _release_orphans
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


def test_the_next_start_takes_a_parked_release_the_page_does_not_hold(
    show_unit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = State.load()
    state.entries[KEY].parked = "hash"
    state.save()
    service = _Service()
    composition.use_engines(monkeypatch, service)
    show_unit.alive = False
    page = _Service()  # держатель страницы: CLAIMS помнит его слабой ссылкой
    CLAIMS.claim("hash", page)
    try:
        _release_orphans(load_config())
    finally:
        CLAIMS.unclaim("hash", page)
    assert (service.dropped, _entry().parked) == ([], "hash"), "страница держит - не трогать"

    _release_orphans(load_config())

    assert (service.dropped, _entry().parked) == (["hash"], "")
