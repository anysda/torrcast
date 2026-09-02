"""Строка автоматического взятия первой живой картины."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def default_taken_line(plans: list[Plan], default: int, asked: str) -> str:
    """Назвать первую живую картину и явную дверь к вопросу."""
    return phrase(
        "choice.default_taken",
        picture=_named(plans[default - 1].picture),
        total=len(plans),
        asked=asked,
    )
