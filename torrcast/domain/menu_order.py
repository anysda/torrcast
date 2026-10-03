"""Правило menu order; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.asked_year import asked_year
from torrcast.domain.franchise_item_key import _franchise_item_key
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture


def menu_order(pictures: list[Picture], query: str = "") -> list[Picture]:
    """Линейка франшизы, а картина года, названного запросом, первой.

    🔴 TC-1398. «Призрак в доспехах 2026» человек берёт из нашего же меню «(2026, сериал)».
    Линейка ставила первым фильм 1995 года как первую часть франшизы, а сериал уезжал в
    хвост, хотя карта его опознала и круг его привёз.
    """
    line = _line(pictures)
    year = asked_year(query)[1] if query else None
    named = [p for p in line if year is not None and p.year == year]
    return named + [p for p in line if all(p is not each for each in named)]


def _line(pictures: list[Picture]) -> list[Picture]:
    picked = [p for p in pictures if not p.collection]
    source = picked or list(pictures)
    keys = {p.franchise for p in source}
    if any(sum(other.startswith(f"{key}-и-") for other in keys) >= 2 for key in keys):
        return sorted(source, key=_franchise_item_key)
    line, tail = _numbered_line(source)
    return line + tail


__all__ = ["menu_order"]
