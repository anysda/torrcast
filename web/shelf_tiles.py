"""Плитка полки под контракт ``GET /api/shelves``: ровно его поля и имя для человека."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture_tile import picture_tile
from torrcast.domain.spoken_title import spoken_title

#: Кто дописывает плиткам обложку; в бою - :data:`hass.hit_posters.hits`.offer.
Offer = Callable[[list[JsonValue]], list[JsonValue]]
#: Тот же ``Passport.of``: раздача сама латиницы не назвала - паспорт добирает её фоном
#: (:func:`web.related_lookup._seed` живёт тем же приёмом).
PassportOf = Callable[[str, bool, float], Origin]
#: Потолок одного паспорта плитки - тот же, что и у родни (:data:`web.related_lookup.TIMEOUT`):
#: фон часовой, а не ответ человеку, и полторы секунды тут ничего не решают.
TIMEOUT = 8.0
#: Ключи, которые контракт ``GET /api/shelves`` разрешает плитке - и ни одного больше.
#: ``shown`` - имя ДЛЯ ЧЕЛОВЕКА (:func:`torrcast.domain.spoken_title.spoken_title`); ``title``
#: остаётся записанным именем ради ``query`` и полки обложек, которые считают по нему же.
_TILE_FIELDS: tuple[str, ...] = (
    "key",
    "title",
    "shown",
    "year",
    "kind",
    "quality",
    "poster",
    "query",
)


def _no_passport(_title: str, _series: bool, _timeout: float) -> Origin:
    """Паспорт по умолчанию: без проводки плитка без своей латиницы остаётся записанной."""
    return Origin()


def shelf_tiles(pictures: list[Any], offer: Offer, passport: PassportOf) -> list[JsonValue]:
    """Плитки картин с предложенной обложкой, ужатые под контракт ``/api/shelves``."""
    seeds: list[JsonValue] = [picture_tile(picture) for picture in pictures]
    return [_project(record, passport) for record in offer(seeds)]


def _project(record: JsonValue, passport: PassportOf) -> JsonValue:
    """Ровно поля контракта; розыскное ``original`` наружу не идёт, а ``shown``
    считается из него, пока он ещё на месте, либо из паспорта, если раздача своей
    латиницы не назвала (:mod:`torrcast.domain.picture_tile`)."""
    if not isinstance(record, dict):
        return record
    title, original = record.get("title"), record.get("original")
    shown = _shown(title, original, passport)
    return {
        field_name: shown if field_name == "shown" else record.get(field_name)
        for field_name in _TILE_FIELDS
    }


def _shown(title: JsonValue, original: JsonValue, passport: PassportOf) -> JsonValue:
    """Имя плитки для человека; неожиданная форма записи остаётся как есть.

    Паспорт зовётся только под английским языком: под русским латиница всё равно
    не покажется (:func:`torrcast.domain.spoken_title.spoken_title`), и звать
    Wikipedia ради ответа, который никто не прочитает, - шум, а не польза.
    """
    if not isinstance(title, str):
        return title
    latin = original if isinstance(original, str) and original else ""
    if not latin and tongue() == EN:
        latin = _latin_of(title, passport)
    return spoken_title(title, latin)


def _latin_of(title: str, passport: PassportOf) -> str:
    """Латиница из паспорта - раздача её не назвала, а Wikipedia может знать."""
    return passport(title, False, TIMEOUT).title


__all__ = ["TIMEOUT", "Offer", "PassportOf", "shelf_tiles"]
