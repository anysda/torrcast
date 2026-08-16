"""Зеркало :mod:`torrcast.domain.run_span`."""

from torrcast.domain.run_span import _run_span


def test_run_span_is_exposed() -> None:
    assert _run_span is not None
