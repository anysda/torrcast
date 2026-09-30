"""Беднее ли круг записанного на диске: промолчал источник, чьи раздачи там лежат.

Лёгший источник (:class:`torrcast.adapters.prowlarr.down_book.DownBook`) круг не беднит: иначе
его раздачи на диске держали бы каждый новый круг на минуте и звали сеть до конца суток записи.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.prowlarr.down_book import DOWN_BOOK, DownBook
from torrcast.usecases.discover.told_circle import ToldCircle
from web.parted import parted

if TYPE_CHECKING:
    from torrcast.usecases.discover.told_indexer import Told
    from torrcast.usecases.select.plan import Plan
    from web.circle_disk import CircleDisk


def poorer_circle(
    disk: CircleDisk | None, key: str, plans: list[Plan], book: DownBook = DOWN_BOOK
) -> bool:
    """Правило :meth:`web.circle_memory.CircleMemory.poorer` для записи ``key``."""
    told = plans.told if isinstance(plans, ToldCircle) else []
    kept = disk.told(key) if disk is not None and told else None
    if not kept or disk is None or (disk.part(key) and not parted(plans)):
        return False
    return bool(_sources(kept) - _sources(told) - book.down())


def _sources(told: list[Told]) -> set[str]:
    return {
        name for said in told for row in said[4] for name in (*row.indexers, row.indexer) if name
    }


__all__ = ["poorer_circle"]
