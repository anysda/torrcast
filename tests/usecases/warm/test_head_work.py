"""Знак захода головы: каталог на полке с номером места, не похожий на кусок."""

from __future__ import annotations

from pathlib import Path

from torrcast.usecases.warm.head_work import head_work


def test_the_mark_names_the_slot_and_is_not_a_piece() -> None:
    """Разные места - разные знаки, и ни один не подходит под ``v*``."""
    shelf = Path("/полка")

    assert head_work(shelf, 0) != head_work(shelf, 3)
    assert head_work(shelf, 3).parent == shelf
    assert not head_work(shelf, 3).name.startswith("v")
