"""Записи для страницы: имя картинки у всех, чьи байты уже здесь, и только у них.

🔴 Имя не только отнимается, но и ВЫДАЁТСЯ. Приговор пачки отвечает целиком, и тридцать
две готовые обложки стояли за сетевым ответом о восьми, которых нет нигде: зритель видел
38 серых плиток из 40 восемь секунд подряд (TC-1268). Полка читается в начале приговора
(:meth:`hass.hit_claims.HitClaims._claim`), а байты ложатся частями
(:func:`hass.poster_parts.poster_parts`), и легшая картинка уходит на экран ближайшим
опросом, не ожидая всей пачки.

Имя картинки - это её собственные название, год и род (:func:`hass.hit_ask._name`), а байты
под ним положил приговор об этой же картине: чужой картинке взяться неоткуда. Тем же
приёмом отдаёт легшее шаг HA, не дождавшийся приговора (:mod:`hass.offer_within`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from hass.hit_ask import _about, _name
from hass.hit_posters import FIELD
from torrcast.domain.json_value import JsonValue


class _Covers(Protocol):
    """Что мост знает о картинках записей (:class:`hass.hit_posters.HitPosters`)."""

    def landed(self, record: JsonValue) -> bool: ...

    def pending(self, records: Sequence[JsonValue]) -> bool: ...

    def due(self, records: Sequence[JsonValue]) -> bool: ...


def shown_covers(results: list[JsonValue], covers: _Covers) -> list[JsonValue]:
    """Те же записи; имя картинки ровно у тех, чьи байты уже лежат на полке."""
    return [_covered(record, covers) for record in results]


def _covered(record: JsonValue, covers: _Covers) -> JsonValue:
    """Запись с именем картинки, если её байты здесь, и без имени, если их ещё нет."""
    if not isinstance(record, dict):
        return record
    if covers.landed(record):
        ask = _about(record)
        return record if ask is None else {**record, FIELD: _name(ask)}
    return {name: value for name, value in record.items() if name != FIELD}


__all__ = ["shown_covers"]
