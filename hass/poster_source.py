"""Откуда список находок берёт постеры: приговор на всю пачку, потом её байты.

Договор разделён на два шага не для красоты. Список обзора ждёт ПРИГОВОР - у этой ли
картины вообще есть статья со сверенным годом, - и ждёт его на месте, потому что имя
картинки уезжает в ту же выдачу. Байты ждать на месте нельзя: десяток картинок из сети
стоил бы человеку секунд перед пустым экраном, и едут они следом, фоном.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from torrcast.domain.facts.ask import Ask


@runtime_checkable
class PosterSource(Protocol):
    """Источник постеров пачкой: сперва приговор по списку статей, потом их байты."""

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        """Каждой картине - её статьи со сверенным годом; нет статьи - пустой список."""
        ...

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        """Байты постеров по вынесенному приговору; чей постер не достался - того нет."""
        ...
