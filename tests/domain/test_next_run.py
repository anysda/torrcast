"""A run of silence grows, ends with an answer, and starts over when it went stale."""

from __future__ import annotations

from torrcast.domain.is_down import DOWN_AFTER, DOWN_WINDOW
from torrcast.domain.next_run import next_run


def test_an_answer_ends_the_run() -> None:
    run = None
    for num in range(DOWN_AFTER):
        run = next_run(run, answered=False, now=1000.0 + num)
    assert run == (DOWN_AFTER, 1000.0 + DOWN_AFTER - 1)
    assert next_run(run, answered=True, now=1200.0) is None


def test_a_silence_after_the_window_starts_over() -> None:
    assert next_run((2, 1000.0), answered=False, now=1000.0 + DOWN_WINDOW + 1) == (
        1,
        1000.0 + DOWN_WINDOW + 1,
    )
