"""Тёзка по имени и году среди картин меню."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.select._plan import _Plan


def _namesake(plans: list[_Plan], number: int, picked: int) -> bool:
    """Тёзка по году: то же название, другая картина.

    Одноимённые части - самая тихая из подмен: в меню они отличаются только годом в
    скобках, и человек, назвавший «мумия», получает «Мумию» - вопрос лишь, которую из
    трёх. Сказать вслух обязаны обе стороны выбора.
    """
    mine, other = plans[picked - 1].picture, plans[number - 1].picture
    return mine.title.casefold() == other.title.casefold() and mine.year != other.year
