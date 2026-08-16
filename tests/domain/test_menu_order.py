"""Зеркало :mod:`torrcast.domain.menu_order`."""

from torrcast.domain.menu_order import menu_order


def test_menu_order_is_exposed() -> None:
    assert menu_order is not None
