"""Зеркало :mod:`torrcast.domain.alt_query`."""

from torrcast.domain.alt_query import alt_query


def test_alt_query_is_exposed() -> None:
    assert alt_query is not None
