"""Обрезка длинной ячейки таблицы: многоточие входит в предел, а не выходит за него."""

from __future__ import annotations

from torrcast.usecases.rank._cut import _cut


def test_a_long_cell_is_cut_with_an_ellipsis() -> None:
    assert _cut("абвгдежзик", 6) == "абв..."
    assert len(_cut("абвгдежзик", 6)) == 6, "иначе колонка разъезжается ровно на многоточие"


def test_a_cell_that_fits_is_left_alone() -> None:
    assert _cut("абвгде", 6) == "абвгде"
    assert _cut("", 6) == ""
