"""Зеркало :mod:`torrcast.domain.watch_ratios`: две доли конца, отвечающие на разные вопросы.

Числа тут завоёваны показом, а не выбраны: «досмотрено» решает, предлагать ли продолжение,
а «титры» - воскрешать ли погасший экран. Живут они вместе ровно затем, чтобы разъехаться
не могли.
"""

from __future__ import annotations

from torrcast.domain.watch_ratios import ENDING_RATIO, WATCHED_RATIO


def test_the_credits_mark_is_never_stricter_than_the_watched_mark() -> None:
    """Сузь долю титров относительно «досмотрено» - и показ полезет воскрешать доигранное.

    Экран гаснет на титрах штатно, и если запись к этому моменту ещё не считает конец
    концом, авария объявляется на ровном месте.
    """
    assert ENDING_RATIO <= WATCHED_RATIO


def test_both_marks_stay_shares_and_not_the_end_of_the_tape() -> None:
    """Единица здесь означала бы «конец ленты», и ни одна из мерок не сработала бы никогда."""
    assert 0.0 < ENDING_RATIO < 1.0
    assert 0.0 < WATCHED_RATIO < 1.0


def test_the_marks_are_generous_enough_to_survive_credits_and_a_lagging_receiver() -> None:
    """Доля щедрая намеренно: последние проценты фильма - титры, и ждать их нельзя.

    Опусти мерку к середине - человек, ушедший на середине, больше не вернулся бы в своё
    место: запись объявила бы картину досмотренной.
    """
    assert ENDING_RATIO >= 0.9
    assert WATCHED_RATIO >= 0.9
