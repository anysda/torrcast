"""Зеркало четвёртой части таблиц разбора имён."""

from torrcast.domain._name_data.data_4 import _MORAS


def test_the_everyday_spelling_of_a_mora_stands_beside_the_strict_one() -> None:
    """«Каэдэ» и «Каэде» - одно имя: ряд с «е» заводится из ряда с «э» и не отстаёт."""
    assert _MORAS["дэ"] == _MORAS["де"] == "de"
