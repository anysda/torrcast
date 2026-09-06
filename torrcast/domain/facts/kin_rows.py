"""Родня картины на диске: ключ ряда и превращение в JSON и обратно.

Зовёт хранилище справки (:mod:`torrcast.adapters.wiki.facts_file_cache`): само оно
умеет только читать и писать словарь целиком, а форму ряда решают правила отсюда - тем
же разделением, каким уже живут паспорта (:mod:`torrcast.domain.facts.cache_rows`).
"""

from __future__ import annotations

from torrcast.domain.facts.kin import Kin
from torrcast.domain.json_value import JsonValue


def _kin_key(entity: str) -> str:
    """Родня лежит в том же файле, что паспорта и справка, но в своём ряду ключей."""
    return f"kin|{entity}"


def _kin_row(found: list[Kin]) -> JsonValue:
    """Список родни в ряд кэша; пустой список - законный ряд «родни нет»."""
    return [{"entity": one.entity, "name": one.name, "year": one.year} for one in found]


def _row_kin(row: JsonValue) -> list[Kin] | None:
    """Ряд кэша в список родни. ``None`` - не спрашивали; пустой список - спрашивали, нет её."""
    if not isinstance(row, list):
        return None
    out: list[Kin] = []
    for item in row:
        if not isinstance(item, dict):
            continue
        year = item.get("year")
        out.append(
            Kin(
                str(item.get("entity", "")),
                str(item.get("name", "")),
                year if isinstance(year, int) else None,
            )
        )
    return out
