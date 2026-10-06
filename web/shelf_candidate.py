"""Тело полок с одной заново собранной полкой - если его стоит показать вместо нынешнего."""

from __future__ import annotations

from datetime import datetime

from torrcast.domain.json_value import JsonValue
from web._stale_tiles import _keep_stale_tiles
from web.built_by_rule import FIELD, RULE
from web.carried import CARRIED, carried
from web.drop_count import DropCount
from web.held_by import held_by


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
    kept, count = _keep_stale_tiles(origin, current, shelf, tiles, drops, limit)
    marks: dict[str, JsonValue] = {name: carried(current, name) for name in ("fresh", "popular")}
    candidate: dict[str, JsonValue] = {
        **current,
        shelf: kept,
        CARRIED: {**marks, shelf: count},
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
    return None


__all__ = ["shelf_candidate"]
