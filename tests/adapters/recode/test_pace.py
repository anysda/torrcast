"""Замер темпа: масштаб таблицы пресетов по факту заходов, и планируем по худшему."""

from __future__ import annotations

from torrcast.adapters.recode.pace import COPY_TOLL, PACE_MEMORY, Pace
from torrcast.adapters.recode.preset_for import REALTIME, preset_for
from torrcast.adapters.recode.presets import PRESETS

#: Цена перекодирующего соседа тем же замером: заход veryfast идёт 0.95x вместо 1.41x.
RECODING_TOLL = 0.70


def test_before_the_first_measurement_we_plan_as_if_the_neighbour_is_copying() -> None:
    """Через 45 с сосед и правда работает - и работает КОПИЕЙ, а она стоит 2-3 %.

    Замер обеих помех на одном входе (кусок 14.3 с, 4 vCPU): рядом с перекодирующим
    прогревом заход veryfast идёт 0.95x вместо 1.41x, рядом с копирующим - 1.38x.
    """
    pace = Pace()

    assert pace.seen == 0
    assert pace.plan == COPY_TOLL == 0.98
    assert pace.table() == tuple((name, speed * 0.98) for name, speed in PRESETS)


def test_a_copying_neighbour_leaves_the_best_preset_reachable() -> None:
    """Цена посылки - не треть скорости, а ступень чёткости: по цене перекодирующего
    соседа лучший пресет идёт медленнее реального времени и не берётся ни при каком
    сроке, сколько бы его ни было."""
    seconds = 14.26
    best = PRESETS[0][0]

    pessimistic = Pace(factor=RECODING_TOLL).table()
    assert pessimistic[0][1] < REALTIME
    assert preset_for(seconds, slack=3600.0, presets=pessimistic) != best

    honest = Pace().table()
    assert honest[0][1] >= REALTIME
    assert preset_for(seconds, slack=3600.0, presets=honest) == best


def test_one_scale_corrects_the_whole_table_at_once() -> None:
    """Заход одним пресетом уточняет срок и для тех, которыми на этом показе не ходили."""
    pace = Pace()
    ratio = pace.record("veryfast", seconds=14.0, spent=10.0)

    assert ratio == 14.0 / 10.0 / dict(PRESETS)["veryfast"]
    assert pace.seen == 1
    assert pace.factor == ratio, "первый замер кладём целиком: до него масштаба нет"
    assert pace.speed("ultrafast") == dict(PRESETS)["ultrafast"] * pace.plan


def test_the_plan_takes_the_worst_of_the_recent_runs_not_their_mean() -> None:
    """Сосед просыпается и засыпает, и среднее по такому ряду - скорость, которой не было."""
    pace = Pace()
    pace.record("veryfast", 14.0, 10.0)  # быстро
    pace.record("veryfast", 7.0, 10.0)  # вдвое медленнее
    pace.record("veryfast", 14.0, 10.0)  # снова быстро

    assert pace.plan == min([pace.factor, *pace.recent])
    assert pace.plan < sum(pace.recent) / len(pace.recent), "среднее было бы враньём в плюс"


def test_only_the_last_few_runs_are_remembered() -> None:
    """Память короткая: старая помеха не должна прижимать план до конца показа."""
    pace = Pace()
    for _ in range(PACE_MEMORY + 3):
        pace.record("veryfast", 14.0, 10.0)

    assert len(pace.recent) == PACE_MEMORY == 3


def test_a_run_that_gave_nothing_is_not_a_measurement() -> None:
    """Сорванный или брошенный заход мерит помеху, а не скорость."""
    pace = Pace()

    assert pace.record("veryfast", 0.0, 10.0) == pace.plan
    assert pace.record("veryfast", 14.0, 0.0) == pace.plan
    assert pace.record("нетакого", 14.0, 10.0) == pace.plan
    assert pace.seen == 0 and pace.recent == []


def test_an_unknown_preset_is_answered_by_the_fastest_speed() -> None:
    """Неизвестное имя не имеет права уронить счёт срока."""
    pace = Pace()

    assert pace.speed("нетакого") == pace.table()[-1][1]
