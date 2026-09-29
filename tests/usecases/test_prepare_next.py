"""Mirror the deferred start of a boundary search."""

from torrcast.usecases.prepare_next import prepare_next


def test_the_deferred_search_factory_is_callable() -> None:
    assert callable(prepare_next)
