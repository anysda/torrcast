"""Зеркало совместимого фасада :mod:`torrcast.selection_bench`."""


def test_selection_bench_facade() -> None:
    from torrcast.selection_bench import _Bench

    assert _Bench.__name__ == "_Bench"
