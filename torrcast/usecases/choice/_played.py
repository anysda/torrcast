"""Отбор релиза выбранной картины с уходом к дублёру, когда играть нечем."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.profile import Profile
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.understudy import understudy
from torrcast.usecases.choice.understudy_note import _why_refused, understudy_note
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.reinforce.late_voice import late_voice

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.ports.progress.progress import Progress
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select.plan import Plan
    from torrcast.usecases.select_bench.bench import Bench


def _late(
    bench: Bench,
    plan: Plan,
    args: Args,
    progress: Progress,
    config: Config,
    profile: Profile,
) -> tuple[Plan, _Prep] | None:
    """Поздний круг поиска озвучки и отбор по добранному; не вышло - ``None``.

    🔴 Ограда тут шире обычной, и намеренно. Круг этот стоит НА ПУТИ ОТКАЗА: всё, что мог,
    отбор уже собрал и сказал, а мы идём смотреть сверх того. Значит любая беда круга -
    отказ службы раздачи, непрочитанный паспорт, пустой ответ - обязана кончиться тем же,
    чем кончился бы заход без него: собранное меню и честная строка остаются на месте.
    Иначе добавка отбирала бы у человека то, что у него уже было.
    """
    try:
        late = late_voice(plan, args, config, progress, profile)
        if late is None:
            return None
        bench.keep_plan(late)
        return late, bench.resolve(late, args, progress)
    except Exception:  # см. докстроку: путь отказа тут шире одной беды
        return None


def _played(
    bench: Bench,
    plans: list[Plan],
    plan: Plan,
    args: Args,
    progress: Progress,
    facts: Facts | None,
    config: Config,
    profile: Profile,
) -> tuple[Plan, _Prep]:
    """Отбор релиза выбранной картины, а нечем играть - её живой тёзки (:func:`understudy`).

    🔴 TC-203. Отдельной функцией это стоит затем, что уход к тёзке - смена КАРТИНЫ, и
    смена эта обязана быть проверяемой отдельно от всего пути показа: печатается строка,
    пишется след, план подменяется целиком (вместе с длительностью из справки и порядком
    прогретого). Возвращается пара «чем в итоге играем» - вызывающему нужны обе половины.

    Кругов ровно два: выбранная картина и одна тёзка. Дальше - честный отказ: перебирать
    меню целиком дороже, чем сказать правду, а цель пути - десять секунд до картинки.
    """
    try:
        prep = bench.resolve(plan, args, progress)
    except _environment_port().not_found_error as refusal:
        # 🔴 TC-770. Отказ гейта озвучки - ещё не конец: спрашивать в ЭТОМ пуле больше
        # некого, но пул собирали по имени, а приговор вынесен по дорожкам
        # (:func:`late_voice`). Поздний круг идёт ПЕРЕД уходом к тёзке: своя картина
        # по-русски лучше чужой.
        late = _late(bench, plan, args, progress, config, profile)
        if late is not None:
            return late
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
    else:
        # Запасной ход отбора отдаёт релиз с чужим звуком и говорит об этом вслух
        # (:meth:`Bench._mute_fallback`). Спросить о нём тот же вопрос, что и об отказе,
        # обязаны: человеку обещан показ ПО-РУССКИ, а не показ любой ценой.
        # Непрочитанный паспорт сюда не относится: «дорожки нет» и «дорожки не читали» -
        # разные ответы, и второй судит нашу спешку, а не релиз (:func:`voice_unproven`).
        voiceless = prep.media is not None and voice_unproven(
            prep.voiced, native=plan.picture.native
        )
        if not args.pinned and voiceless:
            late = _late(bench, plan, args, progress, config, profile)
            if late is not None:
                return late
        return plan, prep
    # Тёзке достаётся ровно то же, что досталось бы ей после меню: своя длительность из
    # справки и свой порядок прогретого (:func:`_timed`, :meth:`Bench.reorder`).
    spare = bench.reorder(spare, _environment_port().timed(spare, facts, args, config, profile))
    bench.keep_plan(spare)
    return spare, bench.resolve(spare, args, progress)
