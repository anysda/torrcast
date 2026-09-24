"""Признак приехавших полок главной: каждая содержит хотя бы одну плитку."""

from __future__ import annotations

from typing import Any, Final

#: Полка приехала, когда в ней есть хотя бы одна настоящая плитка. Это планка наличия,
#: не цель полноты: короткая полка публикуется и принимается. Добор останавливается по
#: фактическому росту ленты (:meth:`web.shelves_cache.ShelvesCache._rebuild`).
FLOOR: Final = 1


def min_tiles(body: dict[str, Any]) -> int:
    """Плиток в самой короткой из двух полок; отсутствующая считается пустой."""
    counts = []
    for key in ("fresh", "popular"):
        shelf = body.get(key)
        counts.append(len(shelf) if isinstance(shelf, list) else 0)
    return min(counts)


__all__ = ["FLOOR", "min_tiles"]
