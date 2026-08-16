"""Правило group weight; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _group_weight(groups: dict[str, list[Picture]], key: str) -> int:
    return sum(len(p.releases) for p in groups[key])


__all__ = ["_group_weight"]
