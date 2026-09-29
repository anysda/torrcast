"""Mirror the isolated search across a torrent boundary."""

from torrcast.usecases.find_next import find_next


def test_the_boundary_search_is_callable() -> None:
    assert callable(find_next)
