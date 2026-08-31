"""Честная строка про картину опоздавшего индексера, которой в меню не было."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.release import Release

if TYPE_CHECKING:
    from torrcast.ports.progress.progress import Progress


KIN_SHOWN = 3


def _foreign_note(foreign: list[Release], menu: frozenset[str], progress: Progress) -> None:
    """Честная строка про картину опоздавшего индексера, которой в меню не было (TC-238).

    Меню напечатано и отвечено, поэтому внести туда новую картину долив не вправе
    никогда - но молчаливых пропаж у нас нет: человек узнаёт, что опоздавший источник
    привёз ещё одну картину, и что в отбор она не пойдёт. Раздачи картин, которые в
    меню ЕСТЬ (``menu`` - ключи показанного списка), строки не получают: сказать про
    них «в списке её не было» значило бы соврать.
    """
    from torrcast.domain.cluster import cluster

    guests = [p for p in cluster(foreign) if p.key not in menu]
    if not guests:
        return
    named = ", ".join(sorted({r.indexer for p in guests for r in p.releases if r.indexer}))
    who = named or phrase("reinforce.late_indexer")
    names = ", ".join(f"«{p.title}» ({p.year or '?'})" for p in guests[:KIN_SHOWN])
    if len(guests) > KIN_SHOWN:
        names += phrase("reinforce.and_more", n=len(guests) - KIN_SHOWN)
    tail = (
        phrase("reinforce.not_listed_singular")
        if len(guests) == 1
        else phrase("reinforce.not_listed_plural")
    )
    progress.note(
        phrase("reinforce.arrived_after_list", who=who)
        + phrase("reinforce.foreign_brought", names=names)
        + tail
    )
