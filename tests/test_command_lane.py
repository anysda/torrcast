"""Зеркало заменяемой полосы команд Telegram."""

import threading

from tgbot.command_lane import CommandLane, _QueuedCommand


def test_only_the_last_command_waits_behind_an_active_one() -> None:
    lane = CommandLane()
    first = _QueuedCommand(["first"], "cast first")
    middle = _QueuedCommand(["middle"], "cast middle")
    last = _QueuedCommand(["last"], "cast last")
    stopped = threading.Event()

    assert lane.offer(first)
    active = lane.take()
    assert lane.replace(middle, lambda: stopped) == "cast first"
    assert lane.replace(last, lambda: stopped) == "cast middle"
    lane.finish(active)

    waiting = lane.take()
    assert waiting.args == ["last"]
    lane.finish(waiting)
    assert lane.occupied() == ""
