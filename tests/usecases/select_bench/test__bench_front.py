"""Зеркало фронта подготовки: кто греется, пока ждут ответа текущего кандидата."""

from __future__ import annotations

from torrcast.domain.pick_settings import PICK_FRONT
from torrcast.usecases.select_bench._bench_front import _bench_front


def test_the_front_starts_at_the_release_being_waited_for() -> None:
    """Первый во фронте - тот, чьего ответа ждут; за ним стоит его смена."""
    assert _bench_front([4, 7, 9, 11], 2)[0] == 7


def test_the_happy_path_does_not_pay_for_the_third_release() -> None:
    """Пока верх ранжира не осуждён, лишний ffprobe соседа никому не нужен."""
    assert len(_bench_front([1, 2, 3, 4, 5], 1)) == PICK_FRONT - 1


def test_a_queue_that_went_past_the_top_warms_the_whole_front() -> None:
    """Очередь пошла дальше верха - дальние кандидаты греются внахлёст с ожиданием."""
    assert _bench_front([1, 2, 3, 4, 5], 2) == [2, 3, 4]


def test_the_tail_of_the_queue_shortens_the_front_by_itself() -> None:
    """У последней попытки греть некого: за ней в очереди никого нет."""
    assert _bench_front([1, 2, 3], 3) == [3]
