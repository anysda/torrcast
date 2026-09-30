"""Checks the short-window pace of Wikipedia requests on a fake clock."""

from torrcast.adapters.wiki.burst_pace import MOST, RESERVE, WINDOW, BurstPace


class _Clock:
    """A clock that moves only when the pace pauses."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def pause(self, seconds: float) -> None:
        self.now += seconds


def test_a_burst_stops_at_the_window_share() -> None:
    """Fifty go at once; the next one is refused when it cannot wait the window out."""
    clock = _Clock()
    pace = BurstPace(clock, clock.pause)
    assert all(pace.admit(0.0) for _ in range(MOST))
    assert not pace.admit(WINDOW - 1.0)
    assert clock.now == 1000.0, "a request that could not outlive the window sat it out"


def test_a_patient_request_goes_when_the_oldest_ages_out() -> None:
    clock = _Clock()
    pace = BurstPace(clock, clock.pause)
    assert all(pace.admit(0.0) for _ in range(MOST))
    assert pace.admit(WINDOW)
    assert clock.now == 1000.0 + WINDOW


def test_a_steady_pace_under_the_share_never_waits() -> None:
    """Four a second for a minute: dev's own tempo is never held."""
    clock = _Clock()
    pace = BurstPace(clock, clock.pause)
    for _ in range(240):
        assert pace.admit(0.0)
        clock.now += 0.25


def test_a_card_text_leaves_the_reserve_to_pictures() -> None:
    """Covers queued 21 s behind card texts: a text stops short, a picture takes the rest."""
    clock = _Clock()
    pace = BurstPace(clock, clock.pause)
    assert all(pace.admit(0.0, background=True) for _ in range(MOST - RESERVE))
    assert not pace.admit(0.0, background=True), "a card text took a reserved slot"
    assert all(pace.admit(0.0) for _ in range(RESERVE))
    assert not pace.admit(0.0)
    assert pace.admit(WINDOW, background=True)
    assert clock.now == 1000.0 + WINDOW, "a card text went before its share aged out"
