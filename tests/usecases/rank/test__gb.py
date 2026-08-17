"""Размер раздачи словами: гигабайты с одним знаком, а ноль - прочерк."""

from __future__ import annotations

from torrcast.usecases.rank._gb import _gb


def test_the_size_is_printed_in_gigabytes_with_one_decimal() -> None:
    assert _gb(8 * 1024**3) == "8.0 ГБ"
    assert _gb(int(1.46 * 1024**3)) == "1.5 ГБ"


def test_a_size_of_zero_is_a_dash_not_a_zero() -> None:
    """Индексер размера не назвал - «0.0 ГБ» было бы враньём о раздаче."""
    assert _gb(0) == "-"
