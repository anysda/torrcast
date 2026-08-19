"""Правило part number; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data.data_2 import _PART_NUMBER_RE, _ROMAN
from torrcast.domain._name_data.data_3 import _FRANCHISE_MIN


def part_number(title: str) -> int | None:
    match = _PART_NUMBER_RE.match(title.strip())
    if not match:
        return None
    head = title[: match.start(1)]
    if len(head.rstrip(" ,-")) < _FRANCHISE_MIN:
        return None
    if re.search("\\d\\s*[-,]\\s*$", head):
        return None
    token = match.group(1).lower()
    return int(token) if token.isdigit() else _ROMAN.get(token)


__all__ = ["part_number"]
