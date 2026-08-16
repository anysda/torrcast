"""Зеркало третьей части таблиц разбора имён."""

from torrcast.domain._name_data.data_3 import THIN_POOL


def test_thin_pool_is_positive() -> None:
    assert THIN_POOL > 0
