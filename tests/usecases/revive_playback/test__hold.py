"""Зеркало держателя показа: круг опроса, конец сеанса и передача погасшего показа лестнице."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

import torrcast.usecases.revive_playback._revive_state as _state
from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import (
    FakeReceiver,
    FakeSupply,
    PlainReceiver,
    feed_with_segments,
)
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.watch import Watch


@pytest.fixture(autouse=True)
def _silent_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """Флажок картинки в зеркале никуда не пишется: меряем решение, а не файл."""
    monkeypatch.setattr(_state, "_revive_playing_mark", lambda _path: None)


def test_a_show_that_cannot_be_raised_ends_by_itself(tmp_path: Path) -> None:
    """Приёмник погас, поднимать нечем - держатель возвращает ответ лестницы, а не висит."""
    receiver = PlainReceiver([(200.0, "PLAYING"), (0.0, "IDLE")])

    ended = _hold(
        cast(Receiver, receiver),
        feed_with_segments(tmp_path),
        clock=FakeClock(now=1000.0),
    )

    assert ended is False, "лестница не поднимала - это обычный конец показа"


def test_a_long_pause_ends_the_show(tmp_path: Path) -> None:
    """Пауза длиной с вечер - показ окончен: юнит гасим, а не держим до утра."""
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver([(100.0, "PLAYING")] + [(100.0, "PAUSED")] * 4000)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False
    assert clock.sleeps, "круг опроса обязан спать между вопросами приёмнику"


def test_a_stuck_pointer_at_the_tail_finishes_the_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Указатель стоит у самого конца дольше минуты - сеанс доигран, и переход не теряется."""
    clock = FakeClock(now=1000.0)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", dur=7200.0, pos=7190.0)
    watch = Watch(key="кино", entry=entry)
    receiver = FakeReceiver([(7190.0, "PLAYING")] * 200)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), watch, clock=clock)

    assert ended is True
    assert "считаю доигранным" in capsys.readouterr().out


def test_a_dead_packing_with_a_healthy_source_falls_honestly(tmp_path: Path) -> None:
    """Упаковка сдалась, источник цел - показ падает честной ошибкой, а не молчанием."""
    feed = feed_with_segments(tmp_path)
    feed.fatal = "ffmpeg лёг"

    with pytest.raises(InfraError, match="упаковка оборвалась"):
        _hold(
            cast(Receiver, FakeReceiver()),
            feed,
            supply=cast(StreamSource, FakeSupply()),
            clock=FakeClock(now=1000.0),
        )
