"""Сторож подвиса: прыгать только вперёд, только на накрытом запасе и не бесконечно."""

from __future__ import annotations

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.cast.nudge import _nudge


def _stuck(receiver: Wired, clock: FakeClock, pos: float, front: float) -> None:
    """Приёмник простоял на одном месте дольше порога сторожа."""
    _nudge(receiver, pos, front)  # первый неподвижный тик - ещё не зависание
    clock.now += receiver.profile.stall_seconds + 1.0
    _nudge(receiver, pos, front)


def test_a_stalled_receiver_is_pushed_forward_past_the_segment(
    tape: Tape,
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
    assert tape.events() == ["nudge"]
    (told,) = tape.named("nudge")
    assert told["to"] == 84.0 + receiver.profile.stall_skip
    assert told["hit"] == 1


def test_a_receiver_waiting_for_us_is_not_pushed_at_all(tape: Tape) -> None:
    """Запас впереди меньше порога - приёмник ждёт НАС, и лечится это упаковкой.

    Прыгнешь - уедешь в неупакованное место и заставишь раздачу паковать заново.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = 84.0

    _stuck(receiver, clock, 84.0, front=84.0 + receiver.profile.ready_ahead - 1.0)

    assert receiver.device.media_controller.jumps == []
    assert tape.events() == []


@pytest.mark.parametrize(
    ("pos", "front"),
    [
        (79.1, 90.0),
        (89.4, 100.0),
        (109.0, 120.0),
        (119.3, 130.0),
        (129.1, 140.0),
        (139.4, 150.0),
        (149.2, 160.0),
        (159.5, 170.0),
        (169.2, 180.0),
    ],
)
def test_a_receiver_starved_on_the_recorded_feed_is_not_pushed(
    tape: Tape, pos: float, front: float
) -> None:
    """Запас 10.8-10.9 с - это наш голод, а не разрешение украсть прыжком 8 с."""
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = pos

    _stuck(receiver, clock, pos, front)

    assert receiver.device.media_controller.jumps == []
    assert tape.events() == []


def test_the_jump_is_measured_by_the_grid_and_not_by_seconds(
    tape: Tape,
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
    tape: Tape, capsys: pytest.CaptureFixture[str]
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
    assert "stopping the jumps" in capsys.readouterr().out


def test_a_jump_that_cannot_get_past_the_shown_frame_is_not_made_at_all(tape: Tape) -> None:
    """Прыжок назад не лечит ничего, поэтому его нет вовсе.

    Прицел берётся от пройденного максимума, а максимум ходит за указателем приёмника -
    и стоит указателю соврать, как прицел уезжает вместе с ним. Замер на живом Q70D:
    картинка стояла на 34.3 с, приёмник отдал ноль позицией - и зритель получил фильм
    сначала. Место последнего показанного кадра тут - пол, ниже которого сторож молчит.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak, receiver._shown = 0.0, 34.3

    _stuck(receiver, clock, 0.0, front=94.3)

    assert receiver.device.media_controller.jumps == []
    assert tape.events() == []
    assert receiver._blind == 0, "несделанный прыжок лестницу не тратит"


def test_the_frame_the_viewer_was_left_on_is_remembered_by_the_first_jump() -> None:
    """Дальше указатель поедет за нашими же прыжками, и спросить о кадре будет некого."""
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._peak = 84.0

    _stuck(receiver, clock, 84.0, front=144.0)

    assert receiver._skip_from == 84.0
