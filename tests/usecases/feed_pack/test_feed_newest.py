"""Брошенный приёмником запрос не уводит упаковку от места, которое тот просит теперь."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

import torrcast.usecases.feed_pack._state as _state
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.feed_pack.feed_newest import _newest

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State


class _Clock:
    """Часы показа, где ожидание старого запроса прерывает новый запрос того же приёмника."""

    def __init__(self) -> None:
        self.now = 100.0
        self.later: list[object] = []

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        while self.later:
            self.later.pop(0)()  # type: ignore[operator]


def test_an_abandoned_request_does_not_pull_the_head_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд 06-10-2026: ТВ ушёл с 12 с на 102 с, а запрос слота 2 ждал файла дальше и
    90 с перезапускал упаковку под себя через раз с запросом слота 11."""
    clock = _Clock()
    monkeypatch.setattr(_state, "clock_port", clock)
    started: list[int] = []

    class Counted(Feed):
        def restart(self, slot: int) -> None:
            started.append(slot)
            if slot == 11:
                (self.out / self.piece_name(slot)).write_bytes(b"x")

    out = hls_dir(str(tmp_path / "hls"))
    feed = Counted(source="", audio=0, out=out, grid=Grid.uniform(7200.0), wait=20.0)

    def seek() -> None:
        clock.now += 2.5  # приёмник перемотан, защёлка прошлого перезапуска уже снята
        assert feed.segment(11) is not None

    clock.later.append(seek)
    assert feed.segment(2) is None, "брошенный запрос дождался файла, которого не просили"

    assert started == [2, 11], f"старый запрос увёл голову обратно: {started}"


def test_a_seam_raised_by_a_newer_warm_request_outranks_an_older_waiting_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Стенд 06-10-2026: -240 с места 105. Запрос прогретого куска поднял упаковку к стыку
    (слот 2), а ждавший с ДО перемотки запрос слота 14 через 2.5 с увёл голову обратно."""
    clock = _Clock()
    monkeypatch.setattr(_state, "clock_port", clock)
    state = cast("_State", SimpleNamespace(asked=0.0, restarted=0.0))
    started: list[int] = []

    def restart(slot: int) -> None:
        state.restarted = clock.now
        started.append(slot)

    def steer(slot: int) -> bool:
        restart(slot)
        return True

    old, _ = _newest(state, steer, restart)
    clock.now += 2.0
    _, seam = _newest(state, steer, restart)
    seam(2)
    clock.now += 2.5
    old(14)

    assert started == [2], f"запрос старого места увёл голову от стыка: {started}"
