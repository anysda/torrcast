"""Правило split franchise index; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data import _TITLE_NUMBER_RE


def split_franchise_index(query: str) -> tuple[str, int | None]:
    match = re.search("^(?P<name>.+?)\\s+(?P<index>\\d{1,2})$", query.strip())
    if not match:
        return (query.strip(), None)
    name = match.group("name").strip()
    if _TITLE_NUMBER_RE.search(name):
        return (query.strip(), None)
    return (name, int(match.group("index")))


__all__ = ["split_franchise_index"]
