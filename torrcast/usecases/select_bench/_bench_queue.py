"""Очередь отбора и её опись: что взято, что отсеяно и почему, - одним событием."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.not_found_error import NotFoundError
from torrcast.ports.journal.slot import journal
from torrcast.usecases.discover.unfit_line import unfit_line
from torrcast.usecases.rank._cut import _cut
from torrcast.usecases.rank.queue_drops import queue_drops
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.start_progress import START

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def _bench_queue(plan: Plan, args: Args) -> list[int]:
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
            phrase(
                "select_bench.skipped_note",
                want=plan.want,
                count=len(skipped),
                name=_cut(skipped[0].raw_name, 60),
            )
        )
    return queue


def _bench_asking(attempt: int, total: int) -> str:
    """Фраза фазы «источник N из M» - и тот же счёт наружу, тому, кто ждёт у экрана.

    Событие одно: очередь дошла до этого источника. В консоль оно уезжает строкой фазы,
    а в браузер - числами (:mod:`torrcast.usecases.start_progress`), потому что страница
    рисует их сама, своим шрифтом и своей полосой. Двух источников счёта у них при этом
    нет: строка и числа считаются здесь, в одном месте, из одной пары чисел.
    """
    START.source(attempt, total)
    return phrase("select_bench.voice_search_phase", number=attempt, total=total)
