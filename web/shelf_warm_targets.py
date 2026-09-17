"""Первые видимые плитки тела полок под заказ прогрева (:mod:`web.warm_targets`)."""

from __future__ import annotations

from typing import Final

from torrcast.domain.json_value import JsonValue
from web.warm_targets import WarmTarget

#: Видимых плиток на экране без прокрутки; прогрев остального ждёт своей очереди.
VISIBLE: Final = 8


def shelf_warm_targets(body: dict[str, JsonValue], later: bool = False) -> list[WarmTarget]:
    """Первые видимые плитки обеих полок; ``later`` - плитки за ними, ближние первыми."""
    shelves = [
        rows if isinstance(rows := body.get(shelf), list) else [] for shelf in ("fresh", "popular")
    ]
    if later:
        depth = max(map(len, shelves))
        tiles = [rows[at] for at in range(VISIBLE, depth) for rows in shelves if at < len(rows)]
    else:
        tiles = [tile for rows in shelves for tile in rows[:VISIBLE]]
    targets: list[WarmTarget] = []
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        title, year, kind = tile.get("title"), tile.get("year"), tile.get("kind")
        if not isinstance(title, str) or not isinstance(year, int) or not isinstance(kind, str):
            continue
        targets.append((str(tile.get("query", "")), str(tile.get("key", "")), title, year, kind))
    return targets


__all__ = ["VISIBLE", "shelf_warm_targets"]
