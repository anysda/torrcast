"""Проверки позиции приёмника."""

from torrcast.domain.position import Position


def test_ratio() -> None:
    assert Position(15, 60).ratio == 0.25
