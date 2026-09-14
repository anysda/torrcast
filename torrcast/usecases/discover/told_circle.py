"""Планы круга вместе с тем, что по дороге сказал каталог.

Запись (:class:`torrcast.usecases.discover.told_indexer.ToldIndexer`) едет самим списком
планов, как и метка урезанного круга: подпись :func:`search_circle` у всех прежняя.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.discover.told_indexer import Told
    from torrcast.usecases.select.plan import Plan


class ToldCircle(list["Plan"]):
    """Планы и запись ответов каталога, по которой круг собирается заново без сети."""

    def __init__(self, plans: Iterable[Plan] = (), told: list[Told] | None = None) -> None:
        super().__init__(plans)
        self.told: list[Told] = told or []


__all__ = ["ToldCircle"]
