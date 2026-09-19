"""Шире, чем выше, - вордмарк или кадр, а не постер; правило общее для обоих источников
картинок (:mod:`torrcast.domain.facts.poster_address`, :mod:`torrcast.adapters.wiki.imdb_rows`).
"""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue


def lying_down(across: JsonValue, down: JsonValue) -> bool | None:
    """Лежачая ли картинка по паре сторон; хоть одна сторона неизвестна - ``None``.

    🔴 ``None`` тут - третий ответ, а не запасное значение ``False``. Стороны в чужом
    ответе бывают не полем вовсе: смена формата у источника оставила бы приговор
    «мусор» на КАЖДОЙ картинке разом, если бы неизвестное читалось как «не лежачая» и
    само молчало ходом дальше, но так же легко и как «лежачая», выбрасывая годные
    постеры навсегда. Различать эти два случая обязан зовущий: он знает, есть ли ещё
    куда попробовать. Квадрат проходит: лежачесть - строгое превышение, а не «не выше».
    """
    wide, high = _side(across), _side(down)
    if not wide or not high:
        return None
    return wide > high


def _side(value: JsonValue) -> int:
    """Сторона картинки числом; поля нет или там не число - ноль."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


__all__ = ["lying_down"]
