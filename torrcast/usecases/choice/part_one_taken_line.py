"""Строка взятия дефолта после стража первой части."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def part_one_taken_line(plans: list[Plan], default: int, asked: str, guard: str) -> str:
    """Сохранить причину стража и назвать взятую вместо первой часть."""
    return phrase(
        "choice.guard_taken",
        guard=guard,
        taken=_named(plans[default - 1].picture),
        asked=asked,
    )
