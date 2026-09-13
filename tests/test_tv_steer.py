"""Пульт каста «На ТВ» над самим приёмником (:func:`web.tv_steer.tv_steer`)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from web.tv_steer import tv_steer


@dataclass
class _Steered(FakeReceiver):
    said: list[tuple[str, float]] = field(default_factory=list)

    def seek(self, pos: float) -> None:
        self.said.append(("seek", pos))

    def pause(self) -> None:
        self.said.append(("pause", 0.0))

    def resume(self) -> None:
        self.said.append(("resume", 0.0))


def test_seekby_counts_from_the_last_heard_report_not_a_fresh_read() -> None:
    # Свежее чтение на излёте отдаёт место десятисекундной давности (`TvSession.stop`).
    receiver = _Steered(Position(100.0, 7200.0, True))
    assert tv_steer(receiver, Position(400.0, 7200.0, True), "seekby", 60.0)
    assert receiver.said == [("seek", 460.0)]
    assert receiver.fronts == []


def test_seekby_without_a_report_reads_the_receiver_and_never_goes_below_zero() -> None:
    receiver = _Steered(Position(30.0, 7200.0, True))
    assert tv_steer(receiver, None, "seekby", -60.0)
    assert receiver.said == [("seek", 0.0)]


def test_toggle_pauses_a_playing_tv_and_resumes_a_paused_one() -> None:
    playing = _Steered(Position(10.0, 7200.0, True))
    paused = _Steered(Position(10.0, 7200.0, False))
    assert tv_steer(playing, None, "toggle", 0.0)
    assert tv_steer(paused, None, "toggle", 0.0)
    assert (playing.said, paused.said) == ([("pause", 0.0)], [("resume", 0.0)])


def test_a_receiver_without_a_remote_is_not_steered() -> None:
    assert not tv_steer(FakeReceiver(Position(10.0, 7200.0, True)), None, "toggle", 0.0)
