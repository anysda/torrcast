"""Снос оставленной раздачи после подъёма показа не затирает записанное показом за время сноса."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes import composition
from tests.usecases.test_worker import _own_show
from tests.usecases.test_worker_parked import _entry, _park, _Service
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.state import State
from torrcast.domain.continue_row import WARM_ROW
from torrcast.usecases.torrents import _release_parked

__all__ = ["_own_show"]  # фикстура юнита показа: запись «Брата» и подделки службы

#: Секунда, которую сторож поднятого показа пишет, пока служба сносит раздачу.
SEEN = 4242.0


class _Watched(_Service):
    """Служба, пока сносит раздачу, даёт сторожу показа записать позицию."""

    def drop(self, torrent_hash: str) -> bool:
        state = State.load()
        state.entries["movie:0:2000"].pos = SEEN
        state.save()
        return super().drop(torrent_hash)


def test_a_position_written_during_the_release_survives_it(
    show_unit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``rem`` идёт уже при живом показе: состояние до сноса устарело, пока служба отвечала."""
    _park(fresher=WARM_ROW)
    service = _Watched()
    composition.use_engines(monkeypatch, service)

    _release_parked(load_config())

    assert (service.dropped, _entry().parked) == (["hash"], "")
    assert State.load().entries["movie:0:2000"].pos == SEEN, "снос затёр позицию живого показа"
