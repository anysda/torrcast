"""Непустое значение строкой, как в публичном фасаде потока.

Зовут его чтение паспорта с полки и разбор звуковой дорожки."""

from __future__ import annotations

from typing import Any


def _opt_str(value: Any) -> str | None:
    """Вернуть непустое значение строкой, как в публичном фасаде потока."""
    return str(value) if value not in (None, "") else None
