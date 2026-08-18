"""Собирает строки сырой выдачи из полей, как их назвал каталог: битые - прочь."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Final, TypeAlias

from torrcast.domain.raw_result import RawResult

_HASH_RE: Final = re.compile(r"^[0-9a-fA-F]{40}$")
#: Сырые поля одной строки выдачи: имя, хэш, размер, сиды, индексер - и в этом порядке.
#: Что в них лежит на самом деле, решает каталог, а не мы: поля приезжают из чужого JSON
#: и чужого XML, и назвать их честнее нечем - ради этой границы адаптер и заведён.
Row: TypeAlias = tuple[Any, ...]


def collect_rows(rows: Iterable[Row]) -> list[RawResult]:
    """Собрать строки выдачи, молча пропуская непригодные (без hash или имени).

    Битая строка выдачи - не отказ поиска: находки остальных обязаны доехать.
    """
    out: list[RawResult] = []
    for row in rows:
        try:
            out.append(_result(row))
        except ValueError:
            continue
    return out


def _result(row: Row) -> RawResult:
    """Собрать строку из сырых полей; без валидного hash она бесполезна.

    Тождество раздачи у нас одно - ``infoHash``, и без него склеивать строку не с чем.
    Не той длины строка - такая же битая: разобрать её всё равно нечем.
    """
    title, info_hash, size, seeders, indexer = row
    text = str(info_hash or "").strip()
    if not _HASH_RE.match(text) or not str(title or "").strip():
        raise ValueError("нет hash или имени")
    return RawResult(str(title), text, _int(size), _int(seeders), str(indexer or ""))


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


__all__ = ["Row", "collect_rows"]
