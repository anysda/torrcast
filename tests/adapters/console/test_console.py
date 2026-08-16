"""Проверяет прежний путь к адаптеру консоли."""

import torrcast.console as facade
from torrcast.adapters.console import console


def test_facade_points_to_adapter() -> None:
    assert facade is console
