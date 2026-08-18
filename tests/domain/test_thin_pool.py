"""Зеркало :mod:`torrcast.domain.thin_pool`: порог, ниже которого пул считается тощим.

Порог отделяет «каталог знает картину другим именем» от «каталог отдал всё, что есть»:
на полной выдаче второй заход по второму имени не зовётся, и цена поиска не удваивается.
"""

from torrcast.domain.thin_pool import THIN_POOL


def test_the_threshold_is_a_row_count_not_a_release_count() -> None:
    """Мера тощего пула - строки выдачи, и порог обязан быть больше одной горстки."""
    assert THIN_POOL == 15
