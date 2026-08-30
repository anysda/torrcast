"""Прогретое на диске в том объёме, в каком его знает лента показа.

Держит его поле :attr:`torrcast.usecases.feed_pack.feed_state._State.vault`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class _Vault(Protocol):
    """Хранилище прогретого в объёме, который нужен показу: взять или отвергнуть кусок.

    Полный :class:`torrcast.usecases.warm.vault.Vault` сюда не приходит: бюджет диска,
    учёт каталогов и вытеснение - дело прогрева, а показу нужны имена файлов.
    """

    def path(self, slot: int) -> Path: ...

    def reject(self, slot: int) -> None: ...

    def head(self) -> Path: ...
