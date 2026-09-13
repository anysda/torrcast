"""Мелкие детали полного тела карточки, вынесенные из HTTP-маршрута."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan


class CardDetails:
    """Небольшие вычисления полного тела карточки."""

    @staticmethod
    def voices(plan: Plan) -> list[JsonValue]:
        """Дорожки как их называют раздачи: студия, лучшее качество и сумма сидов.

        ТЗ называет источником ``Release.dubbed`` - это булево, имени в нём нет. Дорожку
        видно только по :attr:`Release.studios`, и группировка идёт по ней.
        """
        lead = {studio.name for studio in plan.ranked[0].studios} if plan.ranked else set()
        groups: dict[str, list[Release]] = {}
        for release in plan.picture.releases:
            for studio in release.studios:
                groups.setdefault(studio.name, []).append(release)
        return [
            {
                "name": name,
                "quality": max(items, key=lambda r: r.height).quality or "",
                "seeders": sum(r.seeders for r in items),
                "default": name in lead,
            }
            for name, items in groups.items()
        ]

    @staticmethod
    def sources_count(releases: list[Release]) -> int:
        """Число разных индексеров, отдавших раздачи картины."""
        names = {release.indexer for release in releases if release.indexer}
        names.update(name for release in releases for name in release.indexers)
        return len(names)

    @staticmethod
    def others(key: str, related: list[JsonValue] | None) -> list[JsonValue] | None:
        """Полка родни без самой открытой картины."""
        if related is None:
            return None
        return [tile for tile in related if not isinstance(tile, dict) or tile.get("key") != key]


__all__ = ["CardDetails"]
