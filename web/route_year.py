"""Год картины из строки маршрута карточки (:mod:`web.preview`)."""

from __future__ import annotations


def route_year(value: str) -> int | None:
    """Год из строки маршрута, только правдоподобное целое."""
    try:
        year = int(value)
    except ValueError:
        return None
    return year if 1800 <= year <= 3000 else None


__all__ = ["route_year"]
