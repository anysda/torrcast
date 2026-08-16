"""Проверяет прежний путь к файловому состоянию."""

import torrcast.state as facade
from torrcast.adapters.filesystem import state


def test_facade_points_to_adapter() -> None:
    assert facade is state
