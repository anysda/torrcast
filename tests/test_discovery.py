"""Зеркало совместимого фасада :mod:`torrcast.discovery`."""


def test_discovery_facade() -> None:
    from torrcast.discovery import _search

    assert callable(_search)
