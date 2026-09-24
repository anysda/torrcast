"""Readers for values declared in ``install.sh`` source text."""

from __future__ import annotations

import re
import shlex


def positive_integer_constant(source: str, name: str, origin: str = "install.sh") -> int:
    """Read one positive integer assignment without confusing its form with absence.

    Quoting a literal does not change its shell value, so both ``NAME=2`` and
    ``NAME="2"`` are accepted. Shell expressions are deliberately not evaluated:
    the guard must stay a source reader and must never execute text it is checking.
    """
    assignments = re.findall(rf"^[ \t]*{re.escape(name)}[ \t]*=(.*)$", source, re.M)
    if not assignments:
        raise AssertionError(f"{origin}: константа {name} не объявлена")
    if len(assignments) != 1:
        raise AssertionError(
            f"{origin}: константа {name} объявлена {len(assignments)} раза, нужна ровно одна"
        )

    raw = assignments[0].strip()
    try:
        words = shlex.split(raw, comments=True, posix=True)
    except ValueError:
        words = []
    if len(words) != 1 or re.fullmatch(r"[+-]?[0-9]+", words[0]) is None:
        raise AssertionError(
            f"{origin}: константа {name} имеет неподдерживаемую форму {raw!r}: "
            "нужен целый числовой литерал (можно в кавычках), потому что $((...)) "
            "в bash не считает дроби; shell-выражения сторож не вычисляет"
        )

    value = int(words[0])
    if value <= 0:
        raise AssertionError(
            f"{origin}: константа {name} должна быть больше нуля, получено {value}"
        )
    return value
