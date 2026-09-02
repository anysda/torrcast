"""Строка взятия сериала там, где под одним именем есть и фильм, и сериал."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.first_alive import first_alive

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def series_taken_line(plans: list[Plan], taken: int, asked: str) -> str:
    """Назвать взятый сериал, оставленный фильм и дверь к списку.

    Обе стороны выбора названы вслух: молчаливая замена картины - худший вид брака, а
    тут дефолт прибора меняется именно на другую картину, и человек обязан прочитать,
    какую и вместо какой.
    """
    return phrase(
        "choice.series_taken",
        picture=_named(plans[taken - 1].picture),
        other=_named(plans[first_alive(plans) - 1].picture),
        asked=asked,
    )


__all__ = ["series_taken_line"]
