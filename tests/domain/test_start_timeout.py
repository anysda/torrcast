"""Зеркало :mod:`torrcast.domain.start_timeout`: сколько ждём ПЕРВОЙ картинки от приёмника.

Сторожится связь с самим приёмником: наше терпение к молчаливому ``IDLE`` обязано пережить
терпение приёмника, иначе мы сдаёмся раньше, чем сдаётся он.
"""

from __future__ import annotations

from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.start_timeout import START_TIMEOUT
from torrcast.usecases.start_budget import START_BUDGET


def test_we_outlive_the_receivers_own_patience_instead_of_giving_up_first() -> None:
    """Пока показ ни разу не начался, ``IDLE`` - это «ещё грузится», а не отказ.

    Ресивер сначала тянет манифест и первый сегмент, и до этого статус остаётся IDLE.
    Опусти срок к терпению самого приёмника - и мы объявляли бы показ несостоявшимся,
    пока приёмник ещё честно пытается его начать.
    """
    assert CAUTIOUS.patience < START_TIMEOUT


def test_our_patience_to_a_silent_receiver_never_outweighs_the_rest_of_the_start() -> None:
    """Терпение к молчаливому ``IDLE`` - слагаемое бюджета старта, а не сам бюджет.

    Срок этот щедрый намеренно, и щедрость его ограничена только снизу - замерами самого
    приёмника. Сверху его держит то, что он не один: за ним стоят метаданные раздачи,
    чтение длительности, карта опорных кадров и пробный прогон. Перевесь он их все вместе -
    и человек ждал бы молчания приёмника дольше, чем всей остальной дороги до картинки.
    """
    assert START_TIMEOUT < START_BUDGET / 2


def test_we_never_give_up_in_the_middle_of_the_receivers_own_retries() -> None:
    """Приёмник сам повторяет LOAD, и наш срок обязан пережить все его попытки.

    Сдайся мы посреди второго повтора - показ, который вот-вот начался бы, гасился бы нами
    же, а причиной в журнале осталось бы «картинки не было», хотя приёмник ещё работал.
    """
    all_retries = (CAUTIOUS.load_retries + 1) * CAUTIOUS.patience

    assert all_retries <= START_TIMEOUT
