"""Проверяет строку сырой выдачи: сборку из полей каталога и отсев непригодных."""

import pytest

from torrcast.adapters.prowlarr.raw_result import RawResult


def test_собирает_строку_из_сырых_полей() -> None:
    row = RawResult.build("Матрица", "a" * 40, "1024", "5", "Knaben")
    assert (row.title, row.info_hash, row.size, row.seeders, row.indexer) == (
        "Матрица",
        "a" * 40,
        1024,
        5,
        "Knaben",
    )


def test_нечисловые_размер_и_сиды_читаются_нулём() -> None:
    """Индексер молчит о размере или врёт видом поля - это не повод ронять строку."""
    row = RawResult.build("Матрица", "a" * 40, None, "много", None)
    assert (row.size, row.seeders, row.indexer) == (0, 0, "")


def test_отрицательные_числа_до_отбора_не_доезжают() -> None:
    assert RawResult.build("Матрица", "a" * 40, -5, -1, "").size == 0


def test_без_валидного_хэша_или_имени_строка_бесполезна() -> None:
    """Тождество раздачи у нас одно - ``infoHash``; без него склеивать её не с чем."""
    for title, info_hash in (("Матрица", "не хэш"), ("Матрица", "a" * 39), ("  ", "a" * 40)):
        with pytest.raises(ValueError, match="нет hash или имени"):
            RawResult.build(title, info_hash, 0, 0, "")


def test_сбор_молча_пропускает_непригодные_строки() -> None:
    """Битая строка выдачи - не отказ поиска: находки остальных обязаны доехать."""
    rows = RawResult.collect(
        [
            ("Матрица", "a" * 40, 1, 2, "Knaben"),
            ("Без хэша", None, 1, 2, "RuTor"),
            ("", "b" * 40, 1, 2, "RuTor"),
        ]
    )
    assert [row.title for row in rows] == ["Матрица"]


def test_magnet_строки_собирается_из_её_же_полей() -> None:
    row = RawResult.build("Матрица", "A" * 40, 1, 2, "Knaben")
    assert row.magnet.startswith(f"magnet:?xt=urn:btih:{'a' * 40}")
    assert "dn=" in row.magnet
