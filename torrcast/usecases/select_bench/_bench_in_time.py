"""Срок отбора нового показа: лучшая раздача ждётся, но кадр обязан встать за пять секунд.

Порядок очереди не меняется, и до срока ждётся тот, чья очередь. После срока ожидание
его приговора больше не держит показ, если в фронте (:func:`_bench_front`) уже готова
годная раздача ниже: русская дорожка подтверждена паспортом, файл без беды, рой
снабжает. Играет лучшая из годных на ту секунду. Замер стенда 15-09: №2 прошёл ffprobe
на 4.19 с, а осуждения №1 (vc1) ждали до 12.86 с.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from torrcast.ports.journal.slot import journal
from torrcast.ports.progress.progress import Progress
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench._bench_supply import _supply_verdict

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select_bench._bench_tally import _Tally
    from torrcast.usecases.select_bench._bench_trouble import _BenchTrouble

#: От клика до первого кадра, секунды: решение владельца.
SHOW_START: Final = 5.0
#: От взятой раздачи до кадра: юнит, LOAD, первый сегмент и его показ (замер резюме 15-09).
AFTER_PICK: Final = 2.0
#: От клика до отбора: картина и круг с диска (замер 15-09, 0.1-1.3 с, половина худшего).
BEFORE_PICK: Final = 0.5
#: Сколько отбор ждёт приговора старшей раздачи, пока младшая годная уже готова.
PICK_IN_TIME: Final = SHOW_START - AFTER_PICK - BEFORE_PICK
#: Шаг, которым после срока проверяются готовые соседи.
_STEP: Final = 0.2


def _in_time(
    bench: _BenchTrouble,
    plan: Plan,
    args: Args,
    prep: _Prep,
    front: list[int],
    progress: Progress,
    prefix: str,
    tally: _Tally,
    deadline: float,
) -> _Prep:
    """Дождаться раздачи ``prep``; после срока взять готовую годную из фронта, если она есть.

    ``deadline`` - потолок фазы отбора (:data:`PICK_BUDGET`), срок считается от его начала.
    Названный руками релиз не подменяется, запасной без русского звука тоже.
    """
    limit = tally.patience(deadline, bench.clock())
    due = deadline - bench.pick_budget + PICK_IN_TIME
    if args.pinned or len(front) < 2:
        bench._wait(prep, progress, prefix=prefix, limit=limit)
        return prep
    if bench.clock() < due and bench._peek(prep, progress, min(due, limit), prefix + prep.phase):
        return prep
    while bench.clock() < limit:
        if prep.ready.wait(_STEP):
            return prep
        progress.phase(prefix + prep.phase)
        for number in front[1:]:
            ready = bench.preps.get((plan.picture.key, number))
            if ready is not None and ready.ready.is_set() and _fit(bench, plan, ready):
                journal().emit("select", "in_time", waited=prep.number, took=number)
                return ready
    bench._wait(prep, progress, prefix=prefix, limit=limit)
    return prep


def _fit(bench: _BenchTrouble, plan: Plan, prep: _Prep) -> bool:
    """Годна ли готовая раздача показу теми же мерками, что и в очереди."""
    trouble = bench._trouble(
        prep,
        pinned=False,
        warn_mbit=plan.warn_mbit,
        recode=plan.recode_at > 0,
        hard_mbit=plan.hard_mbit,
    )
    if trouble or voice_unproven(prep.voiced, native=plan.picture.native):
        return False
    # Подмена покупает время, а кусок тяжелее потолка приёмника пережимается на ходу: 22.5 Мбит
    # «Выжившего» отдали первый сегмент за 4.4 с вместо 0.6 у копии (стенд 15-09).
    heavy = prep.media and prep.video and prep.media.weight_mbit(prep.video.size) > plan.recode_at
    if plan.recode_at > 0 and heavy:
        return False
    ratio = _supply_verdict(bench.profile, prep)[0]
    return ratio < 0 or ratio >= bench.profile.supply_ratio
