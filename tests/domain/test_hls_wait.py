"""Зеркало :mod:`torrcast.domain.hls_wait`: сроки карты опорных кадров и пробного прогона.

Оба срока - слагаемые бюджета старта, и сторожится ровно это: каждый обязан быть заметно
короче суммы, в которую входит, и заметно длиннее той цены, ради которой заведён.
"""

from __future__ import annotations

from torrcast.domain.hls_wait import KEYS_WAIT, PILOT_TIMEOUT
from torrcast.usecases.start_budget import START_BUDGET

#: Обычная цена пробного прогона в один кадр на тёплом входе.
PILOT_USUAL_SECONDS = 1.7


def test_the_two_waits_together_stay_the_smaller_half_of_the_start_budget() -> None:
    """Подготовка нарезки - часть пути до картинки, и часть меньшая.

    Остальное в бюджете - это метаданные раздачи, чтение длительности и терпение приёмника
    к молчаливому ``IDLE``, то есть фазы, без которых картинки не будет вовсе. Перевесь их
    подготовка - и показ упирался бы в нарезку там, где ждать надо было приёмник.
    """
    assert KEYS_WAIT + PILOT_TIMEOUT < START_BUDGET / 2


def test_the_pilot_deadline_is_a_deadline_and_not_the_usual_price() -> None:
    """Потолок пробного прогона стоит на порядок выше обычной его цены.

    Обычно прогон стоит 0.5-1.7 с, но на холодном рое это чтение нового места, и упирается
    оно в раздачу. Опусти потолок к обычной цене - и холодный рой стал бы отказом старта
    вместо ожидания.
    """
    assert PILOT_TIMEOUT >= 10 * PILOT_USUAL_SECONDS
