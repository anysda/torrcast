"""Выбор пресета: успеть к сроку, не опускаясь ниже реального времени."""

from __future__ import annotations

from torrcast.adapters.recode.preset_for import DEADLINE_MARGIN, REALTIME, preset_for


def test_a_roomy_deadline_buys_the_best_picture() -> None:
    """Срок в сто секунд на десять секунд фильма берёт самый качественный пресет."""
    assert preset_for(10.0, 100.0) == "veryfast"


def test_a_tighter_deadline_steps_down_the_ladder() -> None:
    """Сто секунд фильма за тот же срок ``veryfast`` уже не успевает."""
    assert preset_for(100.0, 100.0) == "superfast"
    assert preset_for(300.0, 100.0) == "ultrafast", "не успел никто - берём самый быстрый"


def test_a_piece_already_playing_gets_the_fastest_preset() -> None:
    """Срок кончился (кусок уже играют) - подгруз хуже ступени чёткости."""
    assert preset_for(10.0, 0.0) == "ultrafast"
    assert preset_for(10.0, -5.0) == "ultrafast"


def test_a_preset_slower_than_real_time_is_never_taken_on_the_show_path() -> None:
    """Срок отвечает «успею ли к ЭТОМУ куску», реальное время - «останется ли следующему».

    Медленный пресет укладывается в щедрый срок вчетверо и всё равно неправ: пока он
    работает, показ не отыгрывает у реального времени ничего.
    """
    slow_then_fast = (("slow", REALTIME - 0.1), ("fast", 2.0))
    assert preset_for(1.0, 1000.0, slow_then_fast) == "fast"


def test_only_half_of_the_deadline_counts_as_in_time() -> None:
    """Срок считается по скорости из прошлого, а сосед просыпается в настоящем.

    Заход на шесть секунд стены при сроке десять в срок НЕ считается: половина срока -
    это запас на разброс 1.43 раза от проснувшегося соседа.
    """
    table = (("exact", 1.0), ("spare", 2.0))
    assert DEADLINE_MARGIN == 0.5
    assert preset_for(6.0, 10.0, table) == "spare", "6 с работы против 5 с половины срока"
    assert preset_for(4.0, 10.0, table) == "exact", "4 с в половину срока укладываются"
