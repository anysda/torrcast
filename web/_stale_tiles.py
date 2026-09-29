"""Плитки прежнего правила на смене отбора: добивают полку, но не спорят с новой.

Смена правила (:mod:`web.built_by_rule`) не вправе ослепить главную: пока новый отбор
идёт, человек видит прежнее тело. Но прежние плитки и не вправе в нём прижиться -
ровно так латиница однажды пережила круг пересборки. Отсюда правило переноса:

- новая сборка стоит первой, прежняя плитка только добивает свободные места до предела
  полки и никогда не вытесняет новую;
- прежняя плитка, которую новый отбор принёс сам или честно отверг (``False``), не
  переносится;
- переносит только первая пересборка нового правила, со всеми её заходами: источник
  переноса - тело на её старте, собранное чужим правилом. Следующая пересборка (через
  час) начинается с тела нового клейма, и перенесённые плитки уходят;
- сколько плиток в хвосте полки перенесено, тело помнит в поле :data:`web.carried.CARRIED`: порог
  усыхания (:func:`web.worth_publishing.worth_publishing`) меряет только своё.
"""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import built_by_rule
from web.drop_count import DropCount


def _keep_stale_tiles(
    origin: dict[str, JsonValue],
    shelf: str,
    tiles: list[JsonValue],
    drops: DropCount,
    limit: int,
) -> tuple[list[JsonValue], int]:
    """Полка для публикации и число перенесённых в её хвост плиток прежнего правила."""
    if built_by_rule(origin):
        return tiles, 0
    old = origin.get(shelf)
    if not isinstance(old, list):
        return tiles, 0
    present = {_tile_key(tile) for tile in tiles}
    gone = present | drops.dropped_keys
    stale = [tile for tile in old if _tile_key(tile) not in gone][: max(limit - len(tiles), 0)]
    return [*tiles, *stale], len(stale)


def _tile_key(tile: JsonValue) -> str | None:
    """Ключ плитки, если старое тело ещё соблюдает контракт API."""
    if not isinstance(tile, dict):
        return None
    key = tile.get("key")
    return key if isinstance(key, str) else None
