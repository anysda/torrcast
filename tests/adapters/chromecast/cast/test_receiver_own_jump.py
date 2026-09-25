"""Скачок самого приёмника после ребуфера не становится перемоткой зрителя."""

from __future__ import annotations

from typing import Any, cast

from tests.adapters.chromecast.cast.wired import Wired
from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.cast.watch_seek import _watch_seek


def _seeks(tape: Tape) -> list[dict[str, Any]]:
    return tape.named("seek")


def _see(receiver: Wired, pos: float, state: str, after: float = 2.0) -> None:
    cast(FakeClock, receiver.clock).now += after
    _watch_seek(receiver, pos, state)


def test_receiver_recovery_jumps_are_not_viewer_seeks(tape: Tape) -> None:
    """После ребуфера приёмник сам уехал вперёд; пульта никто не касался.

    Это две записи проблемного сеанса: 9:53 -> 10:26 и 11:38 -> 12:25.
    До правки обе становились ``seek`` и давали в итоге ``перемоток 2``.
    """
    receiver = Wired(clock=FakeClock(now=100.0))

    _see(receiver, 593.0, "PLAYING", 0.0)
    _see(receiver, 593.0, "BUFFERING")
    _see(receiver, 626.0, "BUFFERING")
    _see(receiver, 626.0 + receiver.PICTURE_STEP, "PLAYING")
    _see(receiver, 698.0, "PLAYING", 72.0)
    _see(receiver, 698.0, "BUFFERING")
    _see(receiver, 745.0, "BUFFERING")
    _see(receiver, 745.0 + receiver.PICTURE_STEP, "PLAYING", 4.6)

    assert _seeks(tape) == [], "собственные скачки приёмника не принадлежат зрителю"


def test_remote_forward_and_backward_seeks_are_still_viewer_seeks(tape: Tape) -> None:
    """С живой картинки пульт по-прежнему различим в обе стороны."""
    receiver = Wired(clock=FakeClock(now=100.0))

    _see(receiver, 593.0, "PLAYING", 0.0)
    _see(receiver, 626.0, "BUFFERING")
    _see(receiver, 626.0 + receiver.PICTURE_STEP, "PLAYING")
    _see(receiver, 698.0, "PLAYING", 72.0)
    _see(receiver, 626.0, "BUFFERING")
    _see(receiver, 626.0 + receiver.PICTURE_STEP, "PLAYING")

    assert [(event["frm"], event["to"]) for event in _seeks(tape)] == [
        (593.0, 626.0),
        (698.0, 626.0),
    ]


def test_own_sender_seek_while_buffering_is_still_a_viewer_seek(tape: Tape) -> None:
    """Страница и HA идут через ``seek``: команда отличает их от автоскачка."""
    receiver = Wired(clock=FakeClock(now=100.0))

    _see(receiver, 593.0, "PLAYING", 0.0)
    _see(receiver, 593.0, "BUFFERING")
    receiver.seek(626.0)
    _see(receiver, 626.0, "BUFFERING")
    _see(receiver, 626.0 + receiver.PICTURE_STEP, "PLAYING")

    assert receiver.device.media_controller.jumps == [626.0]
    assert [(event["frm"], event["to"]) for event in _seeks(tape)] == [(593.0, 626.0)]
