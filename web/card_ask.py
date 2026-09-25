"""Что страница спросила у карточки (:mod:`web.card`) сверх ключа картины."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class CardAsk:
    """Запрос круга, принесённое имя, язык дорожек, вкладка и их долгий добор."""

    query: str = ""
    lang: str = ""
    season: int | None = None
    voices: bool = False
    shown: str = ""

    @classmethod
    def of(cls, query: Mapping[str, str]) -> CardAsk:
        """Мусорный номер вкладки не ошибка: сезон выберет первая доступная вкладка."""
        tab = query.get("season", "")
        season = int(tab) if tab.isdigit() and 0 < int(tab) <= 40 else None
        voices = query.get("voices") == "1"
        return cls(
            query.get("query", ""),
            query.get("lang", ""),
            season,
            voices,
            query.get("shown", "").strip(),
        )


#: Карточка, у которой страница ничего сверх ключа не спросила.
NO_ASK: Final = CardAsk()

__all__ = ["NO_ASK", "CardAsk"]
