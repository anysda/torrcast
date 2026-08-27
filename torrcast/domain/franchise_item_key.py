"""Правило franchise item key; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _franchise_item_key(picture: Picture) -> tuple[bool, int, bool, int, int, str]:
    # Привязанная картина стоит СРАЗУ ЗА своей датированной половиной (``year is None``
    # третьим членом): живая датированная несёт русский голос и берётся первой, а её
    # бесстрочная половина - следующей, впереди всех более поздних лет.
    return (
        picture.sort_year is None,
        picture.sort_year or 0,
        picture.year is None,
        picture.part or 99,
        -len(picture.releases),
        picture.title,
    )


__all__ = ["_franchise_item_key"]
