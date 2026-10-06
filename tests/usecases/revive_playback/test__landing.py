"""Перемотка с пульта ТВ при касте с карточки: цель и буфер в записи сразу (:mod:`_landing`)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from tests.fakes.clock import FakeClock
from tests.fakes.state_store import FakeStateStore
from tests.usecases.revive_playback.world import PlainReceiver, feed_with_segments
from torrcast.domain.entry import Entry
from torrcast.domain.position import Position
from torrcast.ports.receiver import Receiver
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.watch import Watch


def _on_disk(tmp_path: Path, script: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """Что лежит в записи на каждом опросе приёмника: место и слово, как их видит мост."""
    state_slot.install(FakeStateStore())
    watch = Watch(key="кино", entry=Entry(title="Кино", magnet="magnet:?xt=1", dur=7200.0))
    seen: list[tuple[float, str]] = []

    class _Checking(PlainReceiver):
        def position(self, front: float = 0.0) -> Position:
            kept = state_slot.store().load().get("кино")
            seen.append((0.0, "") if kept is None else (round(kept.pos, 1), kept.paused))
            return super().position(front)

    receiver = _Checking([*script, (0.0, "IDLE")])
    _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), watch, clock=FakeClock(1000.0))
    return seen


def test_a_remote_seek_names_its_target_and_the_buffer_before_the_first_frame(
    tmp_path: Path,
) -> None:
    """Стенд 06-10-2026, «Play on TV» с карточки, пульт «+600» со 119.9: ТВ 14 с в буфере на
    719.9, а запись до первого кадра держала 113.7 и ``PLAYING`` - карточка шла часами."""
    seen = _on_disk(
        tmp_path,
        [
            (117.9, "PLAYING"),
            (119.9, "PLAYING"),
            *[(719.9, "BUFFERING")] * 3,
            (721.0, "PLAYING"),
            (723.0, "PLAYING"),
        ],
    )

    assert seen[3:6] == [(719.9, "BUFFERING")] * 3, "запись не назвала ни цели, ни буфера"
    assert seen[6] == (721.0, "PLAYING"), "ТВ заиграл - слово буфера не снято"


def test_the_watchdog_nudges_in_a_buffer_do_not_move_the_bookmark(tmp_path: Path) -> None:
    """Сторож подвиса двигает указатель в буфере по 8 с (замер на Q70D: 12 прыжков, 1:36
    вперёд кадра). Это не перемотка: в закладку идёт показанный кадр, а не указатель."""
    seen = _on_disk(
        tmp_path,
        [(100.0, "PLAYING"), (102.0, "PLAYING")]
        + [(pos, "BUFFERING") for pos in (102.0, 110.0, 118.0, 126.0)],
    )

    assert seen[3:7] == [(102.0, "BUFFERING")] * 4, "подвис увёл закладку туда, где кадра не было"
