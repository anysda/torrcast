"""Счёт раздач, отсеянных до очереди, по причинам; зовёт строка итога отбора."""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.release import Release
from torrcast.usecases.rank.drop_reason import _Judged, drop_reason
from torrcast.usecases.rank.off_season import _pinned, off_season


class _Counted(_Judged, Protocol):
    """План в объёме, который нужен счёту: пул в ранжире и отсев по именам сезонов."""

    ranked: list[Release]
    off_season: int


def queue_drops(plan: _Counted, queue: list[int], pinned: bool = False) -> dict[str, int]:
    """Сколько раздач картины выкинуто до очереди и по каким причинам.

    Считается ПО ПУЛУ КАРТИНЫ, а не по :attr:`Plan.ranked`: раздачи, у которых нет
    нужного сезона, отсекаются ещё при сборке плана (:func:`plan_for`) и до сих пор не
    попадали ни в одну строку вовсе. Поэтому сумма очереди и всех причин сходится с
    длиной ``plan.picture.releases`` — это и есть проверка того, что счёт полон.

    Свёрткой, а не событием на раздачу, — намеренно: 895 событий на один запрос это не
    диагностика, а способ переполнить очередь записи, из которой события теряются молча
    (:class:`torrcast.adapters.filesystem.trace_journal.writer._Writer`).

    ``pinned`` — релиз назван руками (``--release N``), и остальные не «выкинуты», а не
    спрошены: причин отбора у них нет.
    """
    counts: dict[str, int] = {}
    if plan.off_season:
        counts[off_season()] = plan.off_season
    taken = set(queue)
    for number, release in enumerate(plan.ranked, start=1):
        if number in taken:
            continue
        why = _pinned() if pinned else drop_reason(release, plan)
        counts[why] = counts.get(why, 0) + 1
    return counts
