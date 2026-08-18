"""Очередь отбора и её опись: что взято, что отсеяно и почему, - одним событием."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.not_found_error import NotFoundError
from torrcast.ports.journal import journal
from torrcast.usecases.discover.unfit_line import unfit_line
from torrcast.usecases.rank._cut import _cut
from torrcast.usecases.rank.queue_drops import queue_drops
from torrcast.usecases.select._plan import _Plan

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Args


def _bench_queue(plan: _Plan, args: Args) -> list[int]:
    """Очередь релизов плана; пустая очередь - это ответ, а не повод подставить отсеянное.

    Пул, очередь и весь отсев с причинами уезжают одним событием на запрос (TC-186).
    Сумма очереди и причин сходится с пулом картины: раздача, не доехавшая до каста,
    больше не исчезает молча (:func:`queue_drops`).

    🔴 TC-432. Ворота не пропустил НИКТО, включая верх ранжира. Подставить отсеянное
    значило бы сыграть игру или репак на запрос сериала - подмена картины, худший вид
    брака. Отказ честный: сколько раздач было, почему каждая не годится и какой у
    человека ход - всё это :func:`unfit_line`.
    """
    queue = plan.candidates(args)
    drops = queue_drops(plan, queue, pinned=args.release is not None)
    journal().emit(
        "select", "queue", pool=len(plan.picture.releases), queued=len(queue), dropped=drops
    )
    if not queue:
        raise NotFoundError(unfit_line(plan, drops, plan.kin))
    if args.release is None and (skipped := plan.skipped):
        # Молчать тут нельзя: человек попросил серию, а половину выдачи мы не взяли.
        print(
            f"серии {plan.want} нет в раздачах: {len(skipped)} "
            f"(«{_cut(skipped[0].raw_name, 60)}»...) - беру ту, где она есть"
        )
    return queue
