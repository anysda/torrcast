"""Честная строка про взятую часть, когда спрошенной части в выдаче не нашлось."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def absent_part_line(plans: list[Plan], default: int, asked: str) -> str:
    """🔴 TC-830. Спрошенной части нет в выдаче: строка называет это, взятую и ``--menu``.

    Причина тут ровно одна, и назвать её обязано именно так: не «спрошенное не играет» -
    оно бы играло, найдись оно. Не нашлось, и потому взято то, что нашлось.

    ⚠️ Взятая названа «первой живой», а не «самой живой», и разойтись этим словам нельзя:
    дефолт у прибора ОДИН (:func:`first_alive`), и он про хронологию, а не про рой. Скажи
    тут «самую живую» - и строка врала бы каждый раз, когда рой больше у поздней части.

    Хвост общий со стражем имени (:func:`named_taken_line`): сколько картин подошло всего
    и ход к остальным. Решение принято за человека, и без хода строка была бы отпиской.
    """
    name, _index = split_franchise_index(asked)
    return phrase(
        "choice.absent_part",
        name=name,
        picture=_named(plans[default - 1].picture),
        total=len(plans),
        asked=asked,
    )
