"""Правило parse source; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data.data_1 import _SOURCES


def _parse_source(text: str) -> str | None:
    for pattern, label in _SOURCES:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


__all__ = ["_parse_source"]
