"""Убирает один забракованный кусок из каталога и памяти раздачи."""

from __future__ import annotations

import contextlib
from collections.abc import MutableSet
from pathlib import Path
from typing import Protocol


class _Vault(Protocol):
    @property
    def served(self) -> MutableSet[int]: ...

    def path(self, slot: int) -> Path: ...

    def spot(self, slot: int) -> Path: ...


def reject(vault: _Vault, slot: int) -> None:
    """Убрать забракованный кусок вместе с меткой точечного перекода."""
    with contextlib.suppress(OSError):
        vault.path(slot).unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        vault.spot(slot).unlink(missing_ok=True)
    vault.served.discard(slot)
