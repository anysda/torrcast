"""Честная строка про картину опоздавшего индексера, которой в меню не было."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.release import Release

if TYPE_CHECKING:
    from torrcast.ports.progress import Progress


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
    who = (
        ", ".join(sorted({r.indexer for p in guests for r in p.releases if r.indexer}))
        or "опоздавший индексер"
    )
    names = ", ".join(f"«{p.title}» ({p.year or '?'})" for p in guests[:KIN_SHOWN])
    if len(guests) > KIN_SHOWN:
        names += f" и ещё {len(guests) - KIN_SHOWN}"
    progress.note(
        f"«{who}» доехал после списка: привёз {names} - "
        + (
            "в списке её не было, в отбор она не пойдёт"
            if len(guests) == 1
            else "в списке их не было, в отбор они не пойдут"
        )
    )
