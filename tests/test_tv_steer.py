"""Пульт каста «На ТВ» над самим приёмником (:func:`web.tv_steer.tv_steer`)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from torrcast.domain.seek_place import END_MARGIN
from web.tv_session import TvSession
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


@pytest.mark.machine
def test_a_seekby_past_the_rest_keeps_the_show_and_its_aim_inside_the_file() -> None:
    """``/api/next`` на ТВ шлёт ``seekby`` с остатком по снимку моста (7000 из 7200), а цель
    :class:`TvSession` считается от доклада приёмника (7100): без предела сумма за файлом."""
    receiver = _Steered(Position(7100.0, 7200.0, True, state="PLAYING"))
    session = TvSession(factory=lambda address, profile: receiver, poll_seconds=0.01)
    heard: list[Position] = []
    session.start("192.0.2.104", "t", "u", 7100.0, echo=heard.append)
    try:
        began = time.monotonic()
        while not heard and time.monotonic() - began < 2.0:
            time.sleep(0.01)
        assert session.steer("seekby", 7200.0 - 7000.0)
        aim = session._aim
    finally:
        session.stop()

    inside = 7200.0 - END_MARGIN
    assert receiver.said == [("seek", inside)], receiver.said
    assert aim == (7100.0, inside), f"цель перемотки за длительностью: {aim}"
