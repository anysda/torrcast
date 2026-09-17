"""Плитка полки под контракт ``GET /api/shelves``: ровно его поля и имя для человека."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.patterns import _CYRILLIC
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture_tile import picture_tile
from torrcast.domain.spoken_title import spoken_title

#: Кто дописывает плиткам обложку; в бою - :data:`hass.hit_posters.hits`.settled.
Offer = Callable[[list[JsonValue]], list[JsonValue]]
#: Играет ли плитка (запрос, ключ); в бою - :meth:`web.shelf_playable.ShelfPlayable.of`.
Playable = Callable[[str, str], bool]
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


def _no_playable(_query: str, _key: str) -> bool:
    """Без проводки отбор играбельности плитку не трогает: она остаётся на полке."""
    return True


def shelf_tiles(
    pictures: list[Any],
    offer: Offer,
    passport: PassportOf,
    playable: Playable = _no_playable,
    limit: int | None = None,
) -> list[JsonValue]:
    """Плитки картин с предложенной обложкой, ужатые под контракт ``/api/shelves``."""
    seeds: list[JsonValue] = [picture_tile(picture) for picture in pictures]
    offered = offer(_spoken(seeds))
    if limit is not None:
        offered = _covered(offered, limit, playable)
    return [_project(record, passport) for record in offered]


def _spoken(seeds: list[JsonValue]) -> list[JsonValue]:
    """Полка главной на языке продукта: под русским картина без русского имени не зовётся.

    Правило то же, что у родни карточки (:func:`web.related_lookup._spoken`): имя не
    переводится, запись без кириллицы просто не попадает на полку - путь имени один
    (TC-956), а выдумывать транслит некому. Под английским полка не меняется ни на
    плитку: латиница там и есть имя показа
    (:func:`torrcast.domain.spoken_title.spoken_title`).

    🔴 Отбор стоит ДО добора обложек и ДО среза :func:`_covered`: место выброшенной
    картины добирает следующий кандидат, а кандидатов собрано втрое против видимых
    плиток (:data:`web.shelves_cache._CANDIDATES`). Признак берётся из самой записи -
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


def _covered(
    records: list[JsonValue], limit: int, playable: Playable = _no_playable
) -> list[JsonValue]:
    """Первые limit записей с обложкой И приговором «играет»: выброшенное добирает следующая.

    Рекомендация без картинки - не рекомендация: полку листают глазами, а не читают.
    «Обложки нет» тут - ПРИГОВОР источника, а не «обложка ещё едет»: в бою сборка ждёт
    байты (:meth:`hass.hit_posters.HitPosters.settled`), и имя остаётся только у легшей
    обложки; обложка, чьи байты не доехали, уступает место следующей картине.

    🔴 Имени нет НИ У ОДНОЙ записи - приговора не было вовсе: источник картинок молчит,
    и отличить «обложки нет» от «не спросили» нечем. Такую сборку отбор не трогает -
    полка из заглушек честнее пустой, - а фон переспросит следующим заходом. Приговор
    играбельности в этом случае тоже не спрашивается - незачем платить дорогим отбором
    (:mod:`web.shelf_playable`) за полку, которую и так не покажут.

    Играбельность стоит дорого (секунды на плитку, TorrServer), а обложка дёшево -
    поэтому плитку без обложки отбор играбельности вовсе не трогает, и очередь идёт по
    покрытым записям, пока не наберёт ``limit`` или не кончится сама.
    """
    covered: list[JsonValue] = [
        record for record in records if isinstance(record, dict) and record.get("poster")
    ]
    if not covered:
        return records[:limit]
    kept: list[JsonValue] = []
    for record in covered:
        if len(kept) >= limit:
            break
        if not isinstance(record, dict):
            continue
        query, key = str(record.get("query", "")), str(record.get("key", ""))
        if playable(query, key):
            kept.append(record)
    return kept


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
