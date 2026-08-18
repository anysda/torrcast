"""Общий инвентарь зеркал отбора: раздача, план картины и запись состояния."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from torrcast.domain.entry import Entry
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan

GB = 1024**3


def release(
    name: str = "Кино / Movie (1999) BDRip 1080p",
    *,
    quality: str = "1080p",
    codec: str = "H.264",
    voices: tuple[str, ...] = ("Дубляж",),
    size_gb: float = 8.0,
    seeders: int = 100,
    magnet: str = "magnet:?xt=кино",
) -> Release:
    """Раздача, которой хватает и на план, и на запись показа."""
    return Release(
        raw_name=name,
        title="Кино",
        year=1999,
        quality=quality,
        codec=codec,
        voices=voices,
        size=int(size_gb * GB),
        seeders=seeders,
        magnet=magnet,
    )


def parsed(name: str, *, seeders: int = 50) -> Release:
    """Раздача, разобранная тем же парсером, что и в бою: с сезонами и сериями."""
    return replace(parse_release_name(name), seeders=seeders)


def plan(*releases: Release, **rest: Any) -> Plan:
    """План по одной картине: пул из переданных раздач в порядке ранжира."""
    pool = list(releases) or [release()]
    fields: dict[str, Any] = {
        "picture": Picture(title="Кино", year=1999, releases=pool),
        "ranked": pool,
        "runtime": 120.0 * 60.0,
        "warn_mbit": 16.0,
    }
    fields.update(rest)
    return Plan(**fields)


def entry(**rest: Any) -> Entry:
    """Запись состояния под ключом картины: то, что читает продолжение."""
    fields: dict[str, Any] = {
        "title": "Кино",
        "magnet": "magnet:?xt=кино",
        "dur": 7200.0,
        "pos": 3600.0,
    }
    fields.update(rest)
    return Entry(**fields)
