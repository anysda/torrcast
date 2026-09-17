"""Счётчик одного прогона отбора: сколько проверено, отброшено, осталось незнанием.

Оборачивает :data:`web.shelf_tiles.Playable`, а не саму полку: считает КАЖДЫЙ честный
вопрос отбору играбельности за один заход добора (:mod:`web.shelves_cache`), сколько
бы плиток он ни проверил в поисках ``limit`` покрытых кандидатов. Доля отброшенных
среди узнанных - защита от неудачного прогона (:func:`web.worth_publishing.
worth_publishing`, TC-1343): «не знаю» не считается ни в числитель, ни в знаменатель,
иначе сетевой сбой читался бы как отсев мусора.
"""

from __future__ import annotations

from dataclasses import dataclass

from web.shelf_tiles import Playable


@dataclass
class DropCount:
    """Счётчик за один заход: сколько проверено, честно отброшено и осталось незнанием."""

    checked: int = 0
    dropped: int = 0
    unknown: int = 0

    def wrap(self, playable: Playable) -> Playable:
        """Обёртка над приговором: считает каждый вызов, самого приговора не меняет."""

        def _counted(query: str, key: str) -> bool | None:
            verdict = playable(query, key)
            self.checked += 1
            if verdict is None:
                self.unknown += 1
            elif verdict is False:
                self.dropped += 1
            return verdict

        return _counted

    @property
    def ratio(self) -> float:
        """Доля отброшенных среди честно узнанных; без узнанных счётчик ничего не роняет."""
        confirmed = self.checked - self.unknown
        return self.dropped / confirmed if confirmed else 0.0


__all__ = ["DropCount"]
