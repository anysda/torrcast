"""Мелкие детали полного тела карточки, вынесенные из HTTP-маршрута."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release


class CardDetails:
    """Небольшие вычисления полного тела карточки."""

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
