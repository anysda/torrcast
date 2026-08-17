"""Зеркало :mod:`torrcast.usecases.start_budget`: сколько CLI ждёт первой картинки.

Сторожится ровно то, ради чего сумма собрана явно: она обязана накрывать ВСЕ фазы, через
которые юнит проходит от запуска до первого кадра. Пока CLI ждал меньше суммы, он гасил
показ, который вот-вот начался бы.
"""

from __future__ import annotations

from torrcast.domain.hls_wait import KEYS_WAIT, PILOT_TIMEOUT
from torrcast.domain.start_settings import START_SLACK
from torrcast.domain.start_timeout import START_TIMEOUT
from torrcast.domain.worker_settings import WORKER_DUR, WORKER_META
from torrcast.usecases.start_budget import START_BUDGET

#: Потолки всех фаз, которые юнит проходит от запуска до первого ``PLAYING``.
PHASES = (WORKER_META, WORKER_DUR, KEYS_WAIT, PILOT_TIMEOUT, START_SLACK, START_TIMEOUT)


def test_the_budget_is_the_sum_of_the_phases_and_not_a_number_taken_with_a_margin() -> None:
    """Бюджет старта - вывод из потолков фаз, а не выбранное на глаз число.

    Развяжи сумму - и она снова разойдётся с фазами: ровно так CLI однажды ждал 120 с там,
    где юнит имел право потратить больше, и гасил показ за секунду до картинки.
    """
    assert sum(PHASES) == START_BUDGET


def test_every_phase_of_the_way_to_the_picture_contributes_something() -> None:
    """Фаза с нулевым потолком выпадает из суммы молча, и бюджет становится короче пути.

    Прочее на пути юнита - запуск, чтение состояния, подъём раздачи - стоит секунд, и
    считать их нулём значит врать себе: именно так CLI однажды и получил бюджет короче
    того, что юнит имел право потратить.
    """
    assert all(phase > 0 for phase in PHASES)
