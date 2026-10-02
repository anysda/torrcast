"""A run of silence grows, ends with an answer, and starts over when it went stale."""

from __future__ import annotations

from torrcast.domain.next_run import next_run


def test_an_answer_ends_the_run() -> None:
    run = None
    for num in range(3):
        run = next_run(run, answered=False, now=1000.0 + num)
    assert run == (3, 1002.0)
    assert next_run(run, answered=True, now=1200.0) is None


def test_a_silence_after_the_window_starts_over() -> None:
    assert next_run((2, 1000.0), answered=False, now=2801.0) == (
        1,
        2801.0,
    )
