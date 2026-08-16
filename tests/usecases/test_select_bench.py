"""Зеркало :mod:`torrcast.usecases.select_bench`."""

from torrcast.usecases.select_bench import _Bench


def test_select_bench_is_available() -> None:
    assert _Bench.__name__ == "_Bench"
