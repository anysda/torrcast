"""Правило seasons in; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.release import Release


def seasons_in(releases: list[Release]) -> tuple[int, ...]:
    """Сезоны, названные вслух самими именами раздач; пусто - имена о сезонах молчат."""
    named = {s for r in releases for s in r.seasons or ((r.season,) if r.season else ())}
    return tuple(sorted(named))


__all__ = ["seasons_in"]
