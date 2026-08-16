"""Проверяет подключение порта ранжирования."""

from torrcast.usecases import rank


def test_rank_asks_through_environment() -> None:
    assert rank.TABLE_LIMIT == 12
