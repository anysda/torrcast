"""One or two silences are not a verdict; three within the window are, until it goes stale."""

from __future__ import annotations

from torrcast.domain.is_down import Run, is_down
from torrcast.domain.next_run import next_run


def _silent(times: int, now: float = 1000.0, step: float = 60.0) -> Run | None:
    run = None
    for num in range(times):
        run = next_run(run, answered=False, now=now + num * step)
    return run


def test_one_or_two_silences_are_not_a_verdict() -> None:
    assert not is_down(_silent(2), 1200.0)
    assert is_down(_silent(3), 1200.0)


def test_silences_further_apart_than_the_window_are_no_run() -> None:
    assert not is_down(_silent(3, step=1801.0), 1000.0 + 3 * 1801.0)


def test_the_verdict_goes_stale_after_the_window() -> None:
    run = _silent(3)
    assert run is not None and not is_down(run, run[1] + 1801.0)
