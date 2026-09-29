"""One or two silences are not a verdict; three within the window are, until it goes stale."""

from __future__ import annotations

from torrcast.domain.is_down import DOWN_AFTER, DOWN_WINDOW, Run, is_down
from torrcast.domain.next_run import next_run


def _silent(times: int, now: float = 1000.0, step: float = 60.0) -> Run | None:
    run = None
    for num in range(times):
        run = next_run(run, answered=False, now=now + num * step)
    return run


def test_one_or_two_silences_are_not_a_verdict() -> None:
    assert not is_down(_silent(DOWN_AFTER - 1), 1200.0)
    assert is_down(_silent(DOWN_AFTER), 1200.0)


def test_silences_further_apart_than_the_window_are_no_run() -> None:
    assert not is_down(_silent(DOWN_AFTER, step=DOWN_WINDOW + 1), 1000.0 + 3 * DOWN_WINDOW)


def test_the_verdict_goes_stale_after_the_window() -> None:
    run = _silent(DOWN_AFTER)
    assert run is not None and not is_down(run, run[1] + DOWN_WINDOW + 1)
