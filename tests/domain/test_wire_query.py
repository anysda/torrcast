"""Зеркало :mod:`torrcast.domain.wire_query`."""

from torrcast.domain.wire_query import wire_query


def test_wire_query_is_exposed() -> None:
    assert wire_query is not None
