"""Строка взятия единственной найденной чужой части."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def lone_other_part_taken_line(plans: list[Plan], asked: str) -> str:
    """Назвать чужую часть, которая всё же взята без ``--menu``."""
    picture = plans[0].picture
    return phrase(
        "choice.lone_other_part_taken",
        name=asked,
        picture=_named(picture),
        part=picture.part,
    )
