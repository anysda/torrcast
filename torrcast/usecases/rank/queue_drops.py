"""Счёт раздач, отсеянных до очереди, по причинам; зовёт строка итога отбора."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.rank.drop_reasons import _PINNED, OFF_SEASON

if TYPE_CHECKING:
    _Plan: TypeAlias = Any


def queue_drops(plan: _Plan, queue: list[int], pinned: bool = False) -> dict[str, int]:
    """Сколько раздач картины выкинуто до очереди и по каким причинам.

    Считается ПО ПУЛУ КАРТИНЫ, а не по :attr:`_Plan.ranked`: раздачи, у которых нет
    нужного сезона, отсекаются ещё при сборке плана (:func:`_plan_for`) и до сих пор не
    попадали ни в одну строку вовсе. Поэтому сумма очереди и всех причин сходится с
    длиной ``plan.picture.releases`` — это и есть проверка того, что счёт полон.

    Свёрткой, а не событием на раздачу, — намеренно: 895 событий на один запрос это не
    диагностика, а способ переполнить очередь записи, из которой события теряются молча
    (:class:`torrcast.trace._Writer`).

    ``pinned`` — релиз назван руками (``--release N``), и остальные не «выкинуты», а не
    спрошены: причин отбора у них нет.
    """
    counts: dict[str, int] = {}
    if plan.off_season:
        counts[OFF_SEASON] = plan.off_season
    taken = set(queue)
    for number, release in enumerate(plan.ranked, start=1):
        if number in taken:
            continue
        why = _PINNED if pinned else drop_reason(release, plan)
        counts[why] = counts.get(why, 0) + 1
    return counts
