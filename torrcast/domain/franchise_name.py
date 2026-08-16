"""Правило franchise name; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data import _FRANCHISE_MIN
from torrcast.domain.unbranded import _unbranded


def franchise_name(title: str) -> str:
    base = re.split("\\s*:\\s*|\\.\\s+|,\\s+или\\s+", _unbranded(title), maxsplit=1)[0]
    cut = re.sub(
        "[\\s,-]+(?:\\d{1,2}(?:\\s*[-,]\\s*\\d{1,2})*|[ivx]{1,4})\\s*$",
        "",
        base,
        flags=re.IGNORECASE,
    )
    if len(cut.rstrip(" -")) >= _FRANCHISE_MIN:
        base = cut
    return base.rstrip(" -")


__all__ = ["franchise_name"]
