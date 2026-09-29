"""Mirror the held result of the early boundary search."""

from torrcast.usecases.prepared_next import PreparedNext


def test_the_prepared_search_is_callable() -> None:
    assert callable(PreparedNext)
