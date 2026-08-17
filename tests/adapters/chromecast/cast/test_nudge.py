"""Сторож подвиса: прыгать только вперёд, только на накрытом запасе и не бесконечно."""

from __future__ import annotations

from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.cast.nudge import _nudge
from torrcast.adapters.filesystem.trace_journal.writer import _Writer


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(_Writer, "put", lambda _self, record: seen.append(record))
    return seen


def _stuck(receiver: Wired, clock: FakeClock, pos: float, front: float) -> None:
    """Приёмник простоял на одном месте дольше порога сторожа."""
    _nudge(receiver, pos, front)  # первый неподвижный тик - ещё не зависание
    clock.now += receiver.profile.stall_seconds + 1.0
    _nudge(receiver, pos, front)


def test_a_stalled_receiver_is_pushed_forward_past_the_segment(
    queued: list[dict[str, Any]],
) -> None:
    """Нудж лечит застрявший КУСОК, и лечится он тем, что кусок перешагивают.

    Замерено на живом Q70D: на 273-й секунде ресивер перестал запрашивать сегменты и
    встал в BUFFERING навсегда - при том что следующий кусок лежал в tmpfs.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = 84.0

    _stuck(receiver, clock, 84.0, front=144.0)

    assert receiver.device.media_controller.jumps == [84.0 + receiver.profile.stall_skip]
    assert [rec["event"] for rec in queued] == ["nudge"]
    assert queued[0]["to"] == round(84.0 + receiver.profile.stall_skip, 1)
    assert queued[0]["hit"] == 1


def test_a_receiver_waiting_for_us_is_not_pushed_at_all(queued: list[dict[str, Any]]) -> None:
    """Запас впереди меньше порога - приёмник ждёт НАС, и лечится это упаковкой.

    Прыгнешь - уедешь в неупакованное место и заставишь раздачу паковать заново.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = 84.0

    _stuck(receiver, clock, 84.0, front=84.0 + receiver.profile.ready_ahead - 1.0)

    assert receiver.device.media_controller.jumps == []
    assert queued == []


def test_the_jump_is_measured_by_the_grid_and_not_by_seconds(
    queued: list[dict[str, Any]],
) -> None:
    """Шаг 8 с, а сегмент бывает и 14.9 с: прыжок короче куска не перешагнёт его никогда.

    Замер на «Моане» 2016: показ встал на 127.2 с внутри куска ``[124.583..137.095)``,
    прыжок целился в 135.2 с, то есть в тот же кусок, и оба нуджа сеанса приземлились
    туда, откуда прыгали.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = 127.2
    receiver.next_cut = lambda _at: 137.095

    _stuck(receiver, clock, 127.2, front=400.0)

    (jump,) = receiver.device.media_controller.jumps
    assert jump == 137.095 + receiver.CUT_SLACK
    assert jump > 127.2 + receiver.profile.stall_skip, "по секундам прыжок не вышел бы из куска"


def test_the_ladder_of_blind_jumps_has_an_end(
    queued: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    """Доказательство того, что нудж вылечил, ровно одно - показанный кадр.

    Ушедший приёмник честно принимает ``seek`` и двигает указатель, оставаясь в
    ``BUFFERING``: замерено 12 нуджей подряд без единого ``PLAYING`` и 96 с фильма
    прошагано впустую.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = 84.0
    limit = receiver.profile.blind_nudges

    for step in range(limit + 2):
        _stuck(receiver, clock, 84.0 + step, front=1000.0)

    assert len(receiver.device.media_controller.jumps) == limit
    assert receiver._gone is True
    assert "прыгать перестаю" in capsys.readouterr().out


def test_the_frame_the_viewer_was_left_on_is_remembered_by_the_first_jump() -> None:
    """Дальше указатель поедет за нашими же прыжками, и спросить о кадре будет некого."""
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = 84.0

    _stuck(receiver, clock, 84.0, front=144.0)

    assert receiver._skip_from == 84.0
