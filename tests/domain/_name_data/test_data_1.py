"""Зеркало первой части таблиц разбора имён."""

from torrcast.domain._name_data.data_1 import _CYRILLIC


def test_cyrillic_table_is_exposed() -> None:
    assert _CYRILLIC.search("кино")
