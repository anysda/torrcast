"""Зеркало :mod:`torrcast.domain.worker_settings`: последние рубежи ожидания ВНУТРИ юнита.

Сторожится то, ради чего эти сроки отделены от бюджетов фазы под меню: здесь магнит юниту
уже отдан, отступать некуда, и ждать тут положено дольше, а не столько же.
"""

from __future__ import annotations

from torrcast.domain.pick_settings import META_BUDGET, PROBE_BUDGET
from torrcast.domain.worker_settings import WORKER_DUR, WORKER_META


def test_the_unit_waits_longer_than_the_menu_because_it_has_nowhere_to_step_aside() -> None:
    """Под меню не уложилась одна раздача - берём следующую; в юните следующей нет.

    Бюджет фазы отбора - это цена ОДНОЙ раздачи из очереди, и не уложилась она значит
    «возьмём соседнюю». В юните магнит уже отдан, соседней нет вовсе, и не приехало значит
    «показывать нечего». Сравняй эти сроки - и юнит начал бы сдаваться на той раздаче,
    которую отбор уже признал живой.
    """
    assert WORKER_META > META_BUDGET
    assert WORKER_DUR > PROBE_BUDGET


def test_reading_the_duration_is_given_more_room_than_waiting_for_the_metadata() -> None:
    """Длительность читается из ПОТОКА, а метаданные - из уже поднятой раздачи.

    Своей длительности следующая серия не знает, и ffprobe за ней лезет в сам поток: это
    дороже, чем дождаться списка файлов, и срок обязан это признавать.
    """
    assert WORKER_DUR > WORKER_META
