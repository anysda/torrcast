"""Слот отказа от подъёма: кто отвечает про отказ человека и кто это назначает."""

from torrcast.ports.abandon.slot import Slot, abandoned, install


def test_a_fresh_slot_says_nobody_called_the_raise_off() -> None:
    """До слова композиционного корня в слоте лежит «не отказывался», а не пустота.

    Умолчание держит консоль: отказаться там некому - команду и человека там зовут одним
    и тем же, - и подъём обязан идти до своего конца.
    """
    slot = Slot()

    assert slot.asked() is False


def test_the_installed_answer_is_what_the_raise_gets() -> None:
    """Назначенное слоям и отдаётся: подъём смотрит в тот же слот."""
    said: list[bool] = [False]
    install(lambda: said[0])

    assert abandoned() is False
    said[0] = True
    assert abandoned() is True


def test_the_slot_answers_the_question_now_and_does_not_remember_the_answer() -> None:
    """Отрицательная проба: слот спрашивает КАЖДЫЙ раз, а не запоминает первый ответ.

    Отказ приходит посреди подъёма, а первый вопрос ему задают до юнита. Запомни слот
    тот первый ответ - и отказ, пришедший секундой позже, не дошёл бы уже никуда.
    """
    asks: list[int] = []

    def _called_off_on_the_second_ask() -> bool:
        asks.append(1)
        return len(asks) > 1

    install(_called_off_on_the_second_ask)

    assert abandoned() is False
    assert abandoned() is True
    assert len(asks) == 2, f"слот спросил {len(asks)} раз вместо двух"


def test_the_installed_answer_can_be_handed_back() -> None:
    """Чужое назначение возвращается на место: этим тесты и живут рядом друг с другом."""
    slot = Slot()
    saved = slot.asking()
    slot.install(lambda: True)

    slot.install(saved)

    assert slot.asked() is False
