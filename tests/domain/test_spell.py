"""Зеркало :mod:`torrcast.domain.spell`."""

from torrcast.domain.spell import spell


def test_spell_is_exposed() -> None:
    assert spell is not None
