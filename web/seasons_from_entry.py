"""Строки серий из закладки: что зритель уже смотрел, чем и где он остановился.

Вынесено из :mod:`web.card_seasons` - там осталось РЕШЕНИЕ, какой сезон и какой раздачей
показать. Правило чистое: ни сети, ни состояния, только запись закладки.
"""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue


def seasons_from_entry(entry: Entry) -> dict[int, list[JsonValue]]:
    """Серии закладки по сезонам; ход и длительность несёт только текущая строка."""
    at = entry.where(entry.season or 0, entry.episode or 0)
    seasons: dict[int, list[JsonValue]] = {}
    for index, row in enumerate(entry.episodes):
        season, episode = row[0], row[1]
        current = index == at
        seasons.setdefault(season, []).append(
            {
                "n": episode,
                "dur": entry.dur if current else 0.0,
                "watched": entry.watched if current else index < at,
                "pos": entry.pos if current else 0.0,
            }
        )
    return seasons


__all__ = ["seasons_from_entry"]
