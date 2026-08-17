"""Зеркало :mod:`torrcast.domain.warm_settings`: где живёт прогретое и сколько ему отведено.

Сторожатся ровно два свойства, ради которых модуль и существует: прогретое лежит на ДИСКЕ,
а не в памяти, и бюджет накрывает худший замеренный вечер с запасом на ошибку прогноза.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from torrcast.domain.warm_settings import WARM_BUDGET, WARM_DIR

#: Худший замеренный вечер: столько прогретого требовалось за один сеанс просмотра.
WORST_EVENING_BYTES = 28_000_000_000

#: Каталоги, которые в этой системе живут в оперативной памяти.
MEMORY_ROOTS = ("/dev/shm", "/run", "/tmp")


def test_the_warm_lives_on_a_disk_and_never_in_memory() -> None:
    """Прогретое - это ЦЕЛЫЙ фильм, и в память он не влезает.

    Уедь каталог по умолчанию в tmpfs - прогрев начал бы вытеснять из памяти сегменты
    показа, ради которого он и греется, а на длинном фильме просто упёрся бы в её конец.
    Это единственный смысл модуля, поэтому и сторожится он первым.
    """
    path = PurePosixPath(WARM_DIR)
    assert path.is_absolute()
    for root in MEMORY_ROOTS:
        assert not path.is_relative_to(root), f"каталог прогретого уехал в память: {WARM_DIR}"


def test_the_budget_covers_the_worst_measured_evening_with_room_for_a_wrong_forecast() -> None:
    """Бюджет обязан накрывать худший замеренный вечер и оставлять запас сверх него.

    Опусти его к самому замеру - и вечер, чуть тяжелее замеренного, начнёт вытеснять
    прогретое из-под идущего показа; запас в два гигабайта и есть цена ошибки прогноза.
    """
    assert WARM_BUDGET >= WORST_EVENING_BYTES
    assert WARM_BUDGET - WORST_EVENING_BYTES >= 2_000_000_000


def test_the_room_for_a_wrong_forecast_stays_a_reserve_and_not_a_second_budget() -> None:
    """Запас сверх замера обязан остаться ЗАПАСОМ: меньше того, что он страхует.

    Запас существует ради ошибки прогноза, а не ради «побольше на всякий случай». Стань он
    больше самого замеренного вечера - и число перестало бы опираться на замер вовсе:
    прогрев занимал бы под себя десятки лишних гигабайт диска, которые ни один вечер не
    просил, и вытеснял бы чужое по бюджету, которого никто не мерил.
    """
    reserve = WARM_BUDGET - WORST_EVENING_BYTES

    assert reserve < WORST_EVENING_BYTES, "запас больше замера - это уже не запас, а догадка"
