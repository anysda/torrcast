"""Правило sorted; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _sorted(pictures: list[Picture]) -> list[Picture]:
    return sorted(
        pictures,
        key=lambda p: (
            p.sort_year is None,
            p.sort_year or 0,
            # Привязанная бесстрочная - сразу за своей датированной половиной (см.
            # :func:`torrcast.domain.anchor_years.anchor_years`), не впереди неё.
            p.year is None,
            p.title,
            p.original or "",
        ),
    )


__all__ = ["_sorted"]
