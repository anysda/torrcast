"""Наследник безмолвной раздачи: следующий по очереди, которого очередь возьмёт и так."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.pick_settings import HEIR_SILENCE
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select_bench._bench_trouble import _BenchTrouble


def _heir(bench: _BenchTrouble, plan: Plan, args: Args, waited: _Prep) -> int | None:
    """Номер сразу за ``waited``, если та молчит без метаданных дольше :data:`HEIR_SILENCE`.

    Подмена сроком не берёт раздачу тяжелее потолка приёмника: перекод на ходу отдаёт
    первый кусок за 4.4 с вместо 0.6, и срока она не выигрывает. Но если ожидаемая так и не
    отдала метаданные, очередь, осудив её, возьмёт ровно следующего - и тоже тяжёлого, и
    тоже с перекодом, только позже. «Оно» (стенд 30-09): №6 молчал все 20 с бюджета, а
    готовый №33 стоял рядом 14 с и сыграл всё равно. Наследнику тяжесть не помеха.

    Ожидаемая, у которой метаданные есть и которая просто долго читается, наследника не
    получает: там ответ близок, и правило подмены прежнее. «Есть» значит пришёл список
    файлов, а не отметка :attr:`_Prep.meta`: её ставят после снятия спроса с TorrServer, и
    этот запрос бывает долгим, а раздача всё это время уже не молчит.
    """
    if waited.files or bench.clock() - waited.started < HEIR_SILENCE:
        return None
    queue = plan.candidates(args)
    at = queue.index(waited.number) + 1 if waited.number in queue else len(queue)
    return queue[at] if at < len(queue) else None
