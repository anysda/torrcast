"""Зеркало совместимого фасада :mod:`torrcast.selection`."""


def test_selection_facade() -> None:
    from torrcast.selection import _Plan

    assert _Plan.__name__ == "_Plan"
