"""Планка полноты полок главной (ТЗ §9): короче двадцати плиток человеку не отдают."""

from __future__ import annotations

from typing import Final

from torrcast.domain.json_value import JsonValue

#: Дословная планка приёмки ТЗ §9: «в каждой полке не меньше 20 плиток». Полка, собранная
#: короче, - признак медленного круга ленты (молчащий индексер не принёс своих строк),
#: а не реальной пустоты каталога: фон добирает её следующими заходами
#: (:meth:`web.shelves_cache.ShelvesCache._rebuild`).
FLOOR: Final = 20


def min_tiles(body: dict[str, JsonValue]) -> int:
    """Плиток в самой короткой из двух полок: планку роняет любая из них."""
    counts = []
    for key in ("fresh", "popular"):
        shelf = body.get(key)
        counts.append(len(shelf) if isinstance(shelf, list) else 0)
    return min(counts)


__all__ = ["FLOOR", "min_tiles"]
