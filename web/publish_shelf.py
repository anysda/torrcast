"""Publish one ready shelf after ordering the work its visible tiles need."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.json_value import JsonValue
from web.drop_count import DropCount
from web.shelf_candidate import shelf_candidate
from web.shelf_warm_targets import shelf_warm_targets
from web.warm_targets import WarmTarget
from web.write_shelves import write_shelves

Warm = Callable[[list[WarmTarget], list[WarmTarget]], object]
Store = Callable[[dict[str, JsonValue]], None]


def publish_shelf(
    current: dict[str, JsonValue],
    origin: dict[str, JsonValue],
    shelf: str,
    tiles: list[JsonValue],
    drops: DropCount,
    *,
    now: datetime,
    limit: int,
    warm: Warm,
    store: Store,
    path: Path,
    complete: bool,
) -> None:
    """Publish a worthwhile candidate, warming only tiles that actually changed.

    Сначала факты плиток, затем публикация: клик по уже видимой полке не ждёт
    единственного рабочего поиска раздач. Повторная запись тех же плиток не меняет
    экран и не вправе заменить очередь единственного фонового рабочего.
    """
    candidate = shelf_candidate(
        current, origin, shelf, tiles, drops, now=now, limit=limit, complete=complete
    )
    if candidate is None:
        return
    changed = candidate.get(shelf) != current.get(shelf)
    published = cast(list[JsonValue], candidate[shelf])
    if changed:
        warmed = {shelf: published}
        try:
            warm(shelf_warm_targets(warmed), shelf_warm_targets(warmed, later=True))
        except Exception:
            # A broken warm-up must not turn an already-built shelf into an invisible one.
            traceback.print_exc()
        else:
            ordered = phrase("systemd.shelf.warmup_ordered", shelf=shelf, count=len(warmed[shelf]))
            print(ordered, flush=True)
    store(candidate)
    print(phrase("systemd.shelf.published", shelf=shelf, count=len(published)), flush=True)
    write_shelves(path, candidate)


__all__ = ["Store", "Warm", "publish_shelf"]
