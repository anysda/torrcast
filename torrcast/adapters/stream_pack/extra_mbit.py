"""Что в контейнере есть, а на ТВ не уезжает: поправка «контейнер → ТВ» в Мбит/с."""

from __future__ import annotations

from torrcast.domain.film_keys import FilmKeys


def extra_mbit(keys: FilmKeys, delivered_mbit: float) -> float:
    """Что в контейнере есть, а на ТВ не уезжает, Мбит/с — по карте и паспорту.

    Ровно то же число, что набирает :meth:`torrcast.adapters.recode.Weights.calibrate` по факту, но
    известное до первого куска. Паспорт молчит (mp4 без тегов) — ноль: тогда потолок веса
    считает по контейнеру целиком, то есть режет с запасом. Запас безопасен, недооценка нет.
    """
    if delivered_mbit <= 0 or len(keys.offset) != len(keys.at) or len(keys.at) < 3:
        return 0.0
    span = keys.at[-1] - keys.at[0]
    if span <= 0:
        return 0.0
    container = (keys.offset[-1] - keys.offset[0]) * 8 / span / 1e6
    return max(0.0, container - delivered_mbit)
