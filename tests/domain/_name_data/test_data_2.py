"""Зеркало второй части таблиц разбора имён."""

from torrcast.domain._name_data.data_2 import _COLLECTION_CUT_RE


def test_collection_table_is_exposed() -> None:
    assert _COLLECTION_CUT_RE.search("Трилогия")
