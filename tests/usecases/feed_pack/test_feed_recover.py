"""A live process with a silent input must not own the next segment forever."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import pytest

from tests.usecases.feed_pack.world import (
    FakeProc,
    factory,
    feed,
    grid,
    here,
    lay,
    packer,
    signals,
    tract,
    vault,
)
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.domain.hls_settings import MUTE_SECONDS
from torrcast.usecases.feed_pack.feed_steer import _steer
from torrcast.usecases.feed_pack.feed_sweep import _sweep

if TYPE_CHECKING:
    from pathlib import Path


def test_silent_live_reader_is_reopened_at_the_end_of_the_warm_shelf(tmp_path: Path) -> None:
    clock = tract(now=1000.0, spawn=here)
    shelf = vault(tmp_path)
    show = feed(tmp_path, vault=shelf, grid=grid(300.0))
    show.packer = packer(tmp_path, edge=8, now=clock.monotonic, rate=1.0, began=900.0)
    show.moved = clock.now
    for slot in range(9):
        lay(show.out, slot)
        lay(shelf.dir, slot)
    asked: list[int] = []
    clock.now += MUTE_SECONDS + 1.0

    _steer(show, 9, asked.append)
    assert show.offline and asked == []  # the request leaves recovery to the clock
    _sweep(show, asked.append)

    assert asked == [9], "a living but silent reader kept the missing segment forever"
    assert show.crashes == 0, "our own recovery is not a crashed ffmpeg"
    assert all((show.out / f"v{slot}.ts").exists() for slot in range(9))


def test_warm_segments_do_not_hide_a_stalled_reader_from_the_clock(tmp_path: Path) -> None:
    clock = tract(now=1000.0, spawn=here)
    shelf = vault(tmp_path)
    show = feed(tmp_path, vault=shelf, grid=grid(300.0))
    show.packer = packer(tmp_path, edge=8)
    for slot in range(15):
        lay(shelf.dir, slot)
    show.moved = clock.now
    asked: list[int] = []
    clock.now += MUTE_SECONDS + 1.0

    _sweep(show, asked.append)

    assert asked == [9] and show.offline
    assert show.front(89.552858) == 150.0


def test_reopening_waits_for_the_new_reader_and_accepts_real_progress(tmp_path: Path) -> None:
    clock = tract(now=1000.0, spawn=here)
    show = feed(tmp_path, vault=vault(tmp_path), grid=grid(300.0))
    show.packer = packer(tmp_path, edge=8)
    show.moved = clock.now
    asked: list[int] = []
    clock.now += MUTE_SECONDS + 1.0
    _sweep(show, asked.append)
    assert asked == [9]

    clock.now += MUTE_SECONDS
    _sweep(show, asked.append)
    assert asked == [9], "the fresh reader needs its own silence allowance"
    clock.now += 1.0
    _sweep(show, asked.append)
    assert asked == [9, 9], "an input that stayed silent must remain recoverable"

    lay(show.packer.run, 9)
    clock.now += 1.0
    _sweep(show, asked.append)
    assert show.offline == "" and show.moved == clock.now
    assert asked == [9, 9], "bytes from the source end the recovery"


@pytest.mark.parametrize("returned_after", [60.0, 90.0])
def test_recovery_terminates_the_old_read_and_delivers_the_missing_segment(
    tmp_path: Path, returned_after: float
) -> None:
    def start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Packer:
        return packer(tmp_path, out=out, run=run, first=first)

    clock = tract(
        now=1000.0,
        spawn=here,
        settle_start=lambda source, want: (want, want),
        packer=factory(start),
    )
    show = feed(tmp_path, vault=vault(tmp_path), grid=grid(300.0))
    old = show.packer = packer(tmp_path, edge=8)
    show.moved = clock.now
    for slot in range(9):
        lay(show.out, slot)
    clock.now += MUTE_SECONDS + 1.0

    show.sweep()

    assert signals(old) == ["terminate"]
    assert show.packer is not None and show.packer is not old
    assert show.packer.first == 9 and show.offline
    assert show.segment(8) == show.out / "v8.ts"
    clock.now = 1000.0 + returned_after
    lay(show.packer.run, 9)
    lay(show.packer.run, 10)
    show.sweep()
    assert show.segment(9) == show.out / "v9.ts"
    assert show.front(89.552858) == 100.0 and not show.offline


def test_recovery_does_not_block_the_clock_or_race_another_restart(tmp_path: Path) -> None:
    workers: list[Callable[[], None]] = []
    clock = tract(now=1000.0, spawn=workers.append)
    show = feed(tmp_path, vault=vault(tmp_path), grid=grid(300.0))
    show.packer = packer(tmp_path, edge=8)
    show.moved = clock.now
    asked: list[int] = []
    clock.now += MUTE_SECONDS + 1.0

    _sweep(show, asked.append)
    clock.now += MUTE_SECONDS + 1.0
    _sweep(show, asked.append)
    assert len(workers) == 1 and asked == []
    assert show.lock.locked(), "only the background lift may own the restart"

    show.fatal = "show ended while the reader was reopening"
    workers.pop()()
    assert asked == [] and not show.lock.locked()


@pytest.mark.parametrize("stopped", ["", "reopening the silent input"])
def test_offline_recovery_survives_a_dead_reader_without_receiver_requests(
    tmp_path: Path, stopped: str
) -> None:
    clock = tract(now=1000.0, spawn=here)
    show = feed(tmp_path, vault=vault(tmp_path), grid=grid(300.0))
    show.packer = packer(tmp_path, edge=8, proc=FakeProc(code=1), stopped=stopped)
    show.offline = "the source is silent"
    show.moved = clock.now
    asked: list[int] = []

    clock.now += MUTE_SECONDS + 1.0
    _sweep(show, asked.append)

    assert asked == [9] and show.offline
    assert show.crashes == 0 and not show.lock.locked()


def test_progress_arriving_before_the_lock_prevents_a_stale_restart(tmp_path: Path) -> None:
    clock = tract(now=1000.0, spawn=here)
    show = feed(tmp_path, vault=vault(tmp_path), grid=grid(300.0))
    show.packer = packer(tmp_path, edge=8)
    show.moved = clock.now
    original = show.lock

    class _ProgressLock:
        def acquire(self, blocking: bool = True) -> bool:
            show.moved = clock.now  # another producer supplied bytes before acquisition
            return original.acquire(blocking=blocking)

        def release(self) -> None:
            original.release()

    show.lock = cast(Any, _ProgressLock())
    asked: list[int] = []
    clock.now += MUTE_SECONDS + 1.0
    _sweep(show, asked.append)

    assert asked == [] and not original.locked()
