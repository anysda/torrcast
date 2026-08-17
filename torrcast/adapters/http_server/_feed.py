"""Что раздаче нужно от поставщика сегментов и ничего сверх того.

Часть, которой пользуются обработчик запросов и :class:`HlsServer`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class _Feed(Protocol):
    """Достаточная для HTTP-адаптера часть поставщика сегментов."""

    out: Path

    def manifest(self) -> bytes: ...

    def segment(self, slot: int) -> Path | None: ...
