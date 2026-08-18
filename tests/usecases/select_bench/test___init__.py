"""Зеркало :mod:`torrcast.usecases.select_bench`."""

from torrcast.usecases.select_bench import Bench


def test_select_bench_is_available() -> None:
    assert Bench.__name__ == "Bench"
