"""Проверяет строку сырой выдачи: её умолчания и неизменность."""

from dataclasses import replace

from torrcast.domain.raw_result import RawResult


def test_несклеенная_строка_приехала_одной_копией() -> None:
    """Пустые списки значат «строка ещё не проходила склейку», а не «индексер молчал»."""
    row = RawResult("Матрица (1999) 1080p", "a" * 40)
    assert (row.copies, row.indexers, row.names) == (1, (), ())
    assert (row.size, row.seeders, row.indexer) == (0, 0, "")


def test_строка_неизменна_и_пересобирается_целиком() -> None:
    """Склейка правит поля только через ``replace``: прежняя строка остаётся прежней."""
    row = RawResult("Матрица (1999) 1080p", "a" * 40, size=1, seeders=2, indexer="Knaben")
    folded = replace(row, seeders=26, copies=3, indexers=("Knaben", "RuTor"))
    assert (folded.seeders, folded.copies, folded.indexers) == (26, 3, ("Knaben", "RuTor"))
    assert (row.seeders, row.copies, row.indexers) == (2, 1, ())
