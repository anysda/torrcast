"""Честная строка стража имени на пути без вопроса: что взято, почему и где варианты."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.named_elsewhere import _unplayable_why
from torrcast.usecases.choice.named_take import _chosen

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def named_taken_line(plans: list[Plan], asked: str, taken: int) -> str:
    """🔴 TC-812. Страж имени взял живейшую: строка называет её, причину и ``--menu``.

    Причин две, и строки две - свести их в одну значило бы соврать про одну из них:

    * названная картина НЕ играет («блич s1e1»: у «Блича» 2004 рой ниже порога живости) -
      об этом сказано словами :func:`_unplayable_why`, а взятая стоит рядом с этой
      причиной, потому что взята она ею, а не живостью самой себя;
    * названные живы («чернобыль s1e5») - тогда взятая просто самая живая ИЗ НИХ, и
      строка так и говорит: критерий взятия - живость роя, показатель того, какую
      картину имели в виду.

    Хвост у обеих один: сколько картин подошло всего и ход к ним - ``--menu``.
    """
    name, _index = split_franchise_index(asked)
    chosen = _chosen(plans, asked)
    whom = ", ".join(phrase("choice.quoted", it=_named(plans[n - 1].picture)) for n in chosen)
    took = _named(plans[taken - 1].picture)
    if alive_numbers(plans, chosen):
        return phrase(
            "choice.named_taken_alive",
            name=name,
            whom=whom,
            took=took,
            total=len(plans),
            asked=asked,
        )
    return phrase(
        "choice.named_taken_unplayable",
        name=name,
        whom=whom,
        why=_unplayable_why(plans, chosen[0], asked_kind(plans)),
        took=took,
        total=len(plans),
        asked=asked,
    )
