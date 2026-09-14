"""Читает явно названные сезоны из имени раздачи."""

from __future__ import annotations

import re
from typing import Final

# Шаблоны адаптированы из PTT (parse-torrent-title), MIT License:
# https://github.com/dreulavelle/PTT/blob/master/PTT/handlers.py
_NAMED: Final = re.compile(
    r"(?:сезон(?:ы|а|ов)?|seasons?)\s*:?\s*№?\s*"
    r"(?P<values>\d{1,2}(?:\s*(?:-|,|/|и|and)\s*s?\d{1,2})*)",
    re.IGNORECASE,
)
_TRAILING: Final = re.compile(
    r"\b(?P<values>\d{1,2}(?:\s*(?:-|,|/|и|and)\s*s?\d{1,2})*)"
    r"\s*(?:й\s*)?сезон(?:ы|а|ов)?\b",
    re.IGNORECASE,
)
_S_SPAN: Final = re.compile(r"\bs\s*(?P<values>\d{1,2}\s*-\s*s?\d{1,2})\b", re.IGNORECASE)
_LIST_SPLIT: Final = re.compile(r"\s*(?:,|/|\bи\b|\band\b)\s*", re.IGNORECASE)
_RANGE: Final = re.compile(r"^(\d{1,2})\s*-\s*s?(\d{1,2})$", re.IGNORECASE)


def _named_seasons(text: str) -> tuple[int, ...]:
    """Вернуть все сезоны, прямо названные одной сезонной пометкой."""
    for pattern in (_S_SPAN, _NAMED, _TRAILING):
        match = pattern.search(text)
        if match and (numbers := _numbers(match.group("values"))):
            return numbers
    return ()


def _numbers(values: str) -> tuple[int, ...]:
    numbers: list[int] = []
    for part in _LIST_SPLIT.split(values):
        span = _RANGE.match(part)
        if span:
            first, last = (int(number) for number in span.groups())
            if not 0 < first < last <= 40:
                return ()
            numbers.extend(range(first, last + 1))
            continue
        if not part.isdigit() or not 0 < int(part) <= 40:
            return ()
        numbers.append(int(part))
    return tuple(dict.fromkeys(numbers))


__all__ = ["_named_seasons"]
