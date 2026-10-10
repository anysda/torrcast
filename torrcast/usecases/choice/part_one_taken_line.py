"""Строка взятия дефолта после стража первой части."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.part_one_guard import part_one_guard

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def part_one_taken_line(plans: list[Plan], default: int, asked: str) -> str:
    """Причина стража и взятая вместо первой часть - одной строкой без противоречия.

    Строка меню кончается «назови номер», а без ``--menu`` номер никто не называет:
    показ начинается сам. Приклеенное к ней «беру первую живую» говорило зрителю
    «сам не включаю» и «включаю» разом, поэтому у взятия свои фразы на ту же причину.
    """
    key, fields = part_one_guard(plans, asked)
    return phrase(
        f"{key}_taken",
        **fields,
        taken=_named(plans[default - 1].picture),
        asked=asked,
    )
