"""Записи картин, которые вообще могут встать плитками полки главной."""

from __future__ import annotations

from typing import Any

from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.facts.patterns import _CYRILLIC
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture_tile import picture_tile

__all__ = ["shelf_seeds"]


def shelf_seeds(pictures: list[Any]) -> list[JsonValue]:
    """Записи картин, которые вообще могут стать плитками: то, о чём спрашивают обложку."""
    return _spoken([picture_tile(picture) for picture in pictures])


def _spoken(seeds: list[JsonValue]) -> list[JsonValue]:
    """Полка главной на языке продукта: под русским картина без русского имени не зовётся.

    Правило то же, что у родни карточки (:func:`web.related_lookup._spoken`): имя не
    переводится, запись без кириллицы просто не попадает на полку - путь имени один
    (TC-956), а выдумывать транслит некому. Под английским полка не меняется ни на
    плитку: латиница там и есть имя показа
    (:func:`torrcast.domain.spoken_title.spoken_title`).

    🔴 Отбор стоит ДО добора обложек и ДО среза :func:`web.shelf_tiles._covered`: место выброшенной
    картины добирает следующий кандидат, а кандидатов собрано втрое против видимых
    плиток (:data:`web.shelf_pictures._CANDIDATES`). Признак берётся из самой записи -
    ни паспорта, ни Wikipedia ради него не зовут: холодный поход стоит секунды, а полка
    собирается фоном на каждую строку ленты.
    """
    if tongue() == EN:
        return seeds
    return [seed for seed in seeds if _speaks_russian(seed)]


def _speaks_russian(record: JsonValue) -> bool:
    """Есть ли у записи русское имя: смотрим записанное ``title``, его и покажут."""
    if not isinstance(record, dict):
        return False
    title = record.get("title")
    return isinstance(title, str) and bool(_CYRILLIC.search(title))
