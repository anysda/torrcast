"""Долива нет: план собран не поиском, и доливать в него нечего."""

from __future__ import annotations

from torrcast.ports.torrent_catalogue import RawRow


def _nothing_late() -> list[RawRow]:
    """Долива нет: план собран не поиском (тесты, отладочные ручки) - доливать нечего."""
    return []
