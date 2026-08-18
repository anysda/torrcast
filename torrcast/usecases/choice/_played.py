"""Отбор релиза выбранной картины с уходом к дублёру, когда играть нечем."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.profile import Profile
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.understudy import understudy
from torrcast.usecases.choice.understudy_note import _why_refused, understudy_note

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.ports.progress import Progress
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select._plan import _Plan
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select_bench._bench import _Bench


def _played(
    bench: _Bench,
    plans: list[_Plan],
    plan: _Plan,
    args: Args,
    progress: Progress,
    facts: Facts | None,
    config: Config,
    profile: Profile,
) -> tuple[_Plan, _Prep]:
    """Отбор релиза выбранной картины, а нечем играть - её живой тёзки (:func:`understudy`).

    🔴 TC-203. Отдельной функцией это стоит затем, что уход к тёзке - смена КАРТИНЫ, и
    смена эта обязана быть проверяемой отдельно от всего пути показа: печатается строка,
    пишется след, план подменяется целиком (вместе с длительностью из справки и порядком
    прогретого). Возвращается пара «чем в итоге играем» - вызывающему нужны обе половины.

    Кругов ровно два: выбранная картина и одна тёзка. Дальше - честный отказ: перебирать
    меню целиком дороже, чем сказать правду, а цель пути - десять секунд до картинки.
    """
    try:
        return plan, bench.resolve(plan, args, progress)
    except _environment_port().not_found_error as refusal:
        spare = understudy(plans, plan)
        if spare is None:
            raise
        why = _why_refused(refusal)
        _environment_port().write(understudy_note(plan, spare, why))
        _environment_port().emit(
            "select",
            "switch",
            **{"from": plan.picture.title, "to": spare.picture.title, "why": why},
        )
    # Тёзке достаётся ровно то же, что досталось бы ей после меню: своя длительность из
    # справки и свой порядок прогретого (:func:`_timed`, :meth:`_Bench.reorder`).
    spare = bench.reorder(spare, _environment_port().timed(spare, facts, args, config, profile))
    bench.keep_plan(spare)
    return spare, bench.resolve(spare, args, progress)
