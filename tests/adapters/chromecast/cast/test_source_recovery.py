"""A receiver reload cannot manufacture the missing continuation."""

from tests.adapters.chromecast.cast.test_position import _Scripted
from tests.adapters.chromecast.cast.wired import Status
from torrcast.adapters.chromecast.cast.position import _position


def test_reload_waits_for_segments_beyond_the_exhausted_buffer() -> None:
    receiver = _Scripted(Status(pos=0.0, state="IDLE", idle_reason="ERROR"))
    receiver._peak = 89.552858

    where = _position(receiver, front=90.0)

    assert not where.playing and where.state == "IDLE"
    assert receiver.loads == [] and receiver._reloads == 0
    assert receiver.restarts == 0

    _position(receiver, front=120.0)
    assert receiver.loads == [89.552858]
