"""Правило picture tile; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture


def picture_tile(picture: Picture) -> dict[str, JsonValue]:
    """Плитка картины без обложки: обёртка отдаёт её тем же путём, что и выдача поиска.

    ``original`` в записи есть, а в контракте ``GET /api/shelves`` - нет: без него
    розыск обложки промахивался бы у картин без русской статьи, ровно как промахивался
    бы список поиска без того же поля (:func:`hass.hit_ask._about`). Под контракт запись
    ужимает зовущий, уже после того, как обложку предложили.
    """
    return {
        "key": picture.key,
        "title": picture.title,
        "year": picture.year,
        "kind": picture.kind,
        "quality": _quality(picture),
        "query": picture.title,
        "original": picture.original or "",
    }


def _quality(picture: Picture) -> str | None:
    """Метка качества плитки: максимум ``Release.quality`` по раздачам картины."""
    named = [release for release in picture.releases if release.quality]
    return max(named, key=lambda release: release.height).quality if named else None


__all__ = ["picture_tile"]
