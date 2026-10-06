"""Тело полок с одной заново собранной полкой - если его стоит показать вместо нынешнего."""

from __future__ import annotations

from datetime import datetime

from torrcast.domain.json_value import JsonValue
from web._stale_tiles import _keep_stale_tiles
from web.built_by_rule import FIELD, RULE
from web.carried import CARRIED, carried
from web.drop_count import DropCount
from web.dropped_marks import DROPPED, dropped_marks
from web.held_by import held_by
from web.shown_pruned import shown_pruned


def shelf_candidate(
    current: dict[str, JsonValue],
    origin: dict[str, JsonValue],
    shelf: str,
    tiles: list[JsonValue],
    drops: DropCount,
    *,
    now: datetime,
    limit: int,
    complete: bool,
    unstamped: bool = False,
) -> dict[str, JsonValue] | None:
    """Новое тело с полкой ``shelf`` на месте прежней; ``None`` - прежнее лучше.

    ``current`` - тело на экране, ``origin`` - тело на старте пересборки: из него, если
    оно собрано чужим правилом, добираются места до ``limit`` (:mod:`web._stale_tiles`).
    Клеймо нового правила ставит только ``complete`` - последняя полка пересборки, поэтому
    первая готовая полка не спорит с прежним телом за планку усыхания.

    ``unstamped`` - холодный заход (:mod:`web.shelf_pass`), который показывает полку до
    приговоров: до клейма такое тело не вправе нести и чужое клеймо, иначе недопроверенный
    показ стал бы планкой усыхания для собственной проверенной полки.
    """
    gone = dropped_marks(current, shelf, drops)
    off = gone[shelf]
    tiles = [tile for tile in tiles if not (isinstance(tile, dict) and _marked(tile, off))]
    kept, count = _keep_stale_tiles(origin, current, shelf, tiles, drops, limit)
    marks: dict[str, JsonValue] = {name: carried(current, name) for name in ("fresh", "popular")}
    candidate: dict[str, JsonValue] = {
        **current,
        shelf: kept,
        CARRIED: {**marks, shelf: count},
        DROPPED: gone,
        "built_at": now.isoformat(),
    }
    if complete:
        candidate[FIELD] = RULE
    elif unstamped:
        candidate.pop(FIELD, None)
    reason = held_by(current, candidate, drops)
    if reason is None:
        return candidate
    print(reason, flush=True)
    return shown_pruned(current, shelf, drops, now)  # the honest drops still leave the screen


def _marked(tile: dict[str, JsonValue], off: JsonValue) -> bool:
    return isinstance(off, list) and tile.get("key") in off


__all__ = ["shelf_candidate"]
