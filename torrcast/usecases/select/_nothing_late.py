"""Долива нет: план собран не поиском, и доливать в него нечего."""

from __future__ import annotations

from torrcast.domain.raw_result import RawResult


def _nothing_late() -> list[RawResult]:
    """Долива нет: план собран не поиском (тесты, отладочные ручки) - доливать нечего."""
    return []
