"""Зеркало :mod:`torrcast.usecases.start_budget`: сколько CLI ждёт первой картинки.

Сторожится ровно то, ради чего сумма собрана явно: она обязана накрывать ВСЕ фазы, через
которые юнит проходит от запуска до первого кадра. Пока CLI ждал меньше суммы, он гасил
показ, который вот-вот начался бы.
"""

from __future__ import annotations

from torrcast.adapters.stream_pack.settle_start import SEEK_BACK_TRIES
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS
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


def _worst_seek_back(step: float, tries: int) -> float:
    """Худший отвод захода назад (TC-1002): шаг сетки, удвоенный на каждой из ``tries`` попыток."""
    return step * 2.0 ** (tries - 1)


def test_the_budget_survives_the_worst_seek_back_of_tc_1002() -> None:
    """TC-1010. Бюджет старта обязан пережить не только фазы пути, но и самый глубокий откат.

    Отвод назад (:data:`torrcast.adapters.stream_pack.settle_start.SEEK_BACK_TRIES`) на
    неудачном заходе способен увести показ на :func:`_worst_seek_back` секунд НИЖЕ
    закладки. Пока бюджет накрывает эту глубину с запасом, показ успевает пересечь
    закладку раньше, чем кончится терпение CLI, и запасной путь ожидания
    (:func:`torrcast.usecases.playback._launch._await_playing`, сверка с настоящим местом
    посадки) остаётся не более чем подстраховкой. Урежь бюджет ниже этой глубины или
    увеличь число попыток отвода - и юнит, честно двигающийся к закладке, будет погашен
    раньше, чем успеет её достичь: это уже не подстраховка, а гарантированная авария.
    """
    worst = _worst_seek_back(HLS_SEGMENT_SECONDS, SEEK_BACK_TRIES)
    assert worst < START_BUDGET, (
        f"бюджет старта {START_BUDGET:.0f} с не покрывает худший отвод назад {worst:.0f} с"
    )
