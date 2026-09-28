"""Сохраняет плитки прежнего правила до нового честного приговора."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import built_by_rule
from web.drop_count import DropCount


def _keep_stale_tiles(
    current: dict[str, JsonValue], shelf: str, tiles: list[JsonValue], drops: DropCount
) -> list[JsonValue]:
    """На смене правила не снимает плитку, пока новый отбор её честно не отверг."""
    if built_by_rule(current):
        return tiles
    old = current.get(shelf)
    if not isinstance(old, list):
        return tiles
    present = {_tile_key(tile) for tile in tiles}
    stale = [tile for tile in old if _tile_key(tile) not in present | drops.dropped_keys]
    return [*tiles, *stale]


def _tile_key(tile: JsonValue) -> str | None:
    """Ключ плитки, если старое тело ещё соблюдает контракт API."""
    if not isinstance(tile, dict):
        return None
    key = tile.get("key")
    return key if isinstance(key, str) else None
