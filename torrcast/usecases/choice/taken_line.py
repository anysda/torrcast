"""Одна честная строка про картину, взятую без вопроса, и ход к любой другой."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def taken_line(plans: list[Plan], default: int, asked: str) -> str:
    """Что взято без вопроса - словами, одной строкой перед показом.

    Решение принято за человека, поэтому строка обязана давать ход: сколько картин
    подошло, где посмотреть их списком и чем назвать другую. Списка на экране в этом
    случае нет вовсе - меню печатается только там, где его читают и на него отвечают,
    а тридцать семь строк перед показом, который уже начался, читать некому.
    """
    return phrase(
        "choice.taken",
        picture=_named(plans[default - 1].picture),
        total=len(plans),
        asked=asked,
    )
