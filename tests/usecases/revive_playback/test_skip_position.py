"""Перешагнутый мёртвый кусок становится новым местом подъёма и закладки."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.adapters.chromecast.cast.wired import Quiet
from tests.fakes.clock import FakeClock
from tests.fakes.state_store import FakeStateStore
from tests.usecases.revive_playback.world import FakeSupply, feed_with_segments
from torrcast.domain.entry import Entry
from torrcast.domain.position import Position
from torrcast.ports.receiver import Receiver
from torrcast.ports.state_store import slot as state_slot
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.watch import Watch


class _DeadAfterEveryLoad(Quiet):
    """Приёмник принимает LOAD, но следующий опрос снова отвечает мёртвой сессией."""

    def __init__(self, clock: FakeClock, progressed: float = 0.0) -> None:
        super().__init__(clock=clock)
        self.asked: list[float] = []
        self.progressed = progressed

    def position(self, front: float = 0.0) -> Position:
        del front
        if self.asked and self.progressed:
            progressed, self.progressed = self.progressed, 0.0
            return Position(progressed, 7200.0, True, "PLAYING")
        return Position(0.0, 7200.0, False, "IDLE")

    def replay(self, at: float, paused: bool = False) -> float:
        self.asked.append(at)
        return super().replay(at, paused)


@pytest.mark.parametrize(("start", "cut"), [(0.0, 20.0), (252.0, 270.0)])
def test_a_skipped_dead_segment_becomes_the_next_attempt_and_saved_place(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _russian_product: None,
    start: float,
    cut: float,
) -> None:
    """Три смерти на куске: попытки 2/3 и resume остаются уже за ним.

    Первые две смерти разыграны штатными повторными LOAD, третья и последующие -
    штатной лестницей подъёма. Состояние счётчика руками не подставляется.
    """
    clock = FakeClock(now=1000.0)
    receiver = _DeadAfterEveryLoad(clock)
    receiver.next_cut = lambda at: cut if at < cut else cut + 20.0
    receiver.play("http://example.test/index.m3u8", at=start)
    assert receiver._reload() is True
    assert receiver._reload() is True
    capsys.readouterr()
    state_slot.install(FakeStateStore())
    entry = Entry(title="Кино", magnet="magnet:?xt=1", dur=7200.0, pos=start)
    watch = Watch(key="кино", entry=entry)

    ended = _hold(
        cast(Receiver, receiver),
        feed_with_segments(tmp_path),
        watch,
        supply=cast(StreamSource, FakeSupply()),
        profile=receiver.profile,
        clock=clock,
        start=start,
    )

    printed = capsys.readouterr().out.splitlines()
    raising = [line for line in printed if "поднимаю показ" in line]
    assert raising == [
        f"приёмник отмолчался - поднимаю показ с {_clock(start)} (попытка 1)",
        f"приёмник отмолчался - поднимаю показ с {_clock(cut)} (попытка 2)",
        f"приёмник отмолчался - поднимаю показ с {_clock(cut)} (попытка 3)",
    ]
    assert receiver.asked == [start, cut + 0.5, cut + 0.5]
    assert ended is True
    assert printed[-1].endswith(f"гашу; cast продолжит с {_clock(cut)}")
    saved = state_slot.store().load().get("кино")
    assert saved is not None and saved.pos == cut + 0.5
    assert saved.moved is False, "пропущенный кусок - не увиденный кадр"


def test_a_receiver_that_progressed_past_the_skip_does_not_get_rolled_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], _russian_product: None
) -> None:
    """Приёмник после прыжка дошёл до 300 с сам: сохранённое место остаётся там, не на 270."""
    clock = FakeClock(now=1000.0)
    receiver = _DeadAfterEveryLoad(clock, progressed=300.0)
    receiver.next_cut = lambda at: 270.0 if at < 270.0 else 320.0
    receiver.play("http://example.test/index.m3u8", at=252.0)
    assert receiver._reload() is True
    assert receiver._reload() is True
    capsys.readouterr()
    state_slot.install(FakeStateStore())
    watch = Watch(
        key="кино",
        entry=Entry(title="Кино", magnet="magnet:?xt=1", dur=7200.0, pos=252.0),
    )

    _hold(
        cast(Receiver, receiver),
        feed_with_segments(tmp_path),
        watch,
        supply=cast(StreamSource, FakeSupply()),
        profile=receiver.profile,
        clock=clock,
        start=252.0,
    )

    assert receiver.asked == [252.0, 300.0, 300.0]
    saved = state_slot.store().load().get("кино")
    assert saved is not None and saved.pos == 300.0


def _clock(seconds: float) -> str:
    """Человеческая позиция для дословной проверки строк продукта."""
    whole = int(seconds)
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"
