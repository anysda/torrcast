"""Отдаёт место раздела, занятое ненужными полками нынешней формы ключа."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm._vault_disk import _dirs, _title, _touched, _weigh


class _Vault(Protocol):
    @property
    def root(self) -> Path: ...

    @property
    def key(self) -> str: ...

    @property
    def keep(self) -> frozenset[str]: ...

    @property
    def floor(self) -> int: ...

    def free(self) -> int: ...


def reclaim_floor(vault: _Vault, need: int) -> int:
    """Освободить под ``need`` байт ненужные полки; вернуть отданные байты.

    Полки прежних форм ключа уже забрал :func:`strip_forms`; здесь остаются полки,
    которые сборка ещё умеет найти, но прямо сейчас они не принадлежат ни этому показу,
    ни соседней серии. Бюджет вправе вытеснить их на том же основании, однако на тесном
    разделе до своего потолка он не доходит. Пол раздела получает симметричное право и
    отдаёт их от самой давней, не сдвигая сам порог.
    """
    mine = {vault.key, *vault.keep}
    shelves = sorted(
        (path for path in _dirs(vault.root) if path.name not in mine),
        key=_touched,
    )
    freed = 0
    while shelves and need + vault.floor > vault.free():
        gone = shelves.pop(0)
        weight = _weigh(gone)
        _state._environment.emit(
            "evict", key=gone.name, freed=weight, need=int(need), title=_title(gone)
        )
        _state._environment.remove_tree(gone)
        freed += weight
    return freed
