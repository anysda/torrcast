"""Продолжение последнего показа: мост передаёт выбор картины и места продукту."""

from __future__ import annotations

from collections.abc import Callable


def _resume(start: Callable[[list[str]], str]) -> str:
    """``POST /api/resume``: поднять показ ровно так, как это делает пустой ``cast``.

    Картину и место выбирает ПРОДУКТ, а не мост: сюда уходит пустой argv, и дальше
    последнее смотренное называет тот же
    :func:`torrcast.usecases.cast_command._default_query._default_query`, а место
    поднимает та же закладка. Складывать это на стороне моста значило бы завести
    второй ответ на один вопрос. Отказ пустому ``query`` у :meth:`play` остаётся:
    показ ПО ЗАПРОСУ без запроса - по-прежнему брак, а это другая просьба.
    """
    return start([])
