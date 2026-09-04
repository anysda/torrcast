"""Правило split titles; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data.data_1 import _CYRILLIC, _LATIN, _TAG_ONLY_RE, _UKRAINIAN
from torrcast.domain.branded_only import _branded_only


def _split_titles(zone: str) -> tuple[str, str | None, tuple[str, ...]]:
    parts = [p.strip(" .-_|,:;") for p in re.split("[/|]", zone)]
    numeric_original = (
        len(parts) == 2 and bool(_CYRILLIC.search(parts[0])) and bool(re.fullmatch("\\d", parts[1]))
    )
    parts = [
        p
        for p in parts
        if (len(p) > 1 or (numeric_original and p.isdigit()))
        and (not _TAG_ONLY_RE.match(p))
        and (not _branded_only(p))
    ]
    if not parts:
        return (zone.strip() or "?", None, ())
    russian = next((p for p in parts if _CYRILLIC.search(p) and (not _UKRAINIAN.search(p))), None)
    latin = next(
        (p for p in parts if (p.isdigit() or _LATIN.search(p)) and (not _CYRILLIC.search(p))), None
    )
    if russian is None:
        return (latin or parts[0], None, ())
    return (russian, latin, tuple(p for p in parts if p != russian and p != latin))


__all__ = ["_split_titles"]
