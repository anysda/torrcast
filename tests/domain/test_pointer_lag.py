"""Зеркало правила подгруза: подгруз доказывает ход указателя, а не слово приёмника."""

from __future__ import annotations

from torrcast.domain.freeze import Freeze
from torrcast.domain.pointer_lag import PointerLag


def _run(lag: PointerLag, ticks: list[tuple[float, float]], playing: bool = True) -> list[Freeze]:
    """Прогнать опросы «(момент, позиция)» и собрать закончившиеся подгрузы."""
    return [done for now, pos in ticks if (done := lag.see(pos, now, playing)) is not None]


def test_a_frozen_pointer_is_a_stall_even_while_the_receiver_says_it_is_playing() -> None:
    """Приставка называет себя играющей всю остановку - подгруз ловится ходом указателя.

    🔴 Ровно этот вход сегодня и молчал: состояние ``PLAYING`` не меняется ни разу, и
    счётчик ребуферов на нём насчитывает ноль при стоящей картинке.
    """
    lag = PointerLag()

    done = _run(lag, [(0.0, 100.0), (2.0, 102.0), (4.0, 102.0), (6.0, 102.0), (8.0, 104.0)])

    assert len(done) == 1, "остановка на два опроса - это один подгруз, а не два"
    assert done[0].pos == 102.0
    assert round(done[0].lost, 2) == 4.0
    assert round(lag.total, 2) == 4.0


def test_an_even_pointer_leaves_no_stalls_and_no_debt() -> None:
    """Отрицательная проба правила: показ вровень с часами подгрузов не даёт."""
    lag = PointerLag()

    done = _run(lag, [(2.0 * k, 100.0 + 2.0 * k) for k in range(20)])

    assert done == []
    assert round(lag.total, 2) == 0.0


def test_the_rounding_jitter_does_not_add_up_to_a_stall() -> None:
    """Дрожь округления знаковая: она гасится в сумме, а порога подгруза не берёт."""
    lag = PointerLag()
    walk = [100.0, 102.4, 103.6, 106.4, 107.6, 110.4, 111.6, 114.0]

    done = _run(lag, [(2.0 * k, pos) for k, pos in enumerate(walk)])

    assert done == []
    assert abs(lag.total) < 0.5


def test_a_watchdog_jump_is_not_playback_and_is_not_counted() -> None:
    """Прыжок сторожа гонит указатель вперёд - ходом показа это не считается."""
    lag = PointerLag()

    done = _run(lag, [(0.0, 100.0), (2.0, 102.0), (4.0, 118.0), (6.0, 120.0)])

    assert done == []
    assert round(lag.total, 2) == 0.0, "прыжок в счёт потерянной плёнки не идёт"


def test_a_pause_is_not_a_stall() -> None:
    """Пауза на пульте - законно стоящий указатель, и плёнку она не отнимает."""
    lag = PointerLag()

    done: list[Freeze] = [
        found
        for now, pos, live in [(0.0, 100.0, True), (2.0, 100.0, False), (4.0, 100.0, False)]
        if (found := lag.see(pos, now, live)) is not None
    ]

    assert done == []
    assert round(lag.total, 2) == 0.0


def test_the_tail_of_a_stall_longer_than_one_poll_stays_inside_it() -> None:
    """Замирание длиннее опроса ложится на два опроса: хвост входит в тот же подгруз."""
    lag = PointerLag()

    done = _run(lag, [(0.0, 100.0), (2.0, 102.0), (4.0, 102.0), (6.0, 103.2), (8.0, 105.2)])

    assert len(done) == 1
    assert round(done[0].lost, 2) == 2.8, "2.0 с остановки плюс 0.8 с хвоста"


def test_our_own_late_poll_is_not_the_viewers_loss() -> None:
    """🔴 Круг опроса, растянувшийся у НАС, мерить показ не может.

    Живая улика: круг длиной 7.3 с, приёмник отдал в нём позицию, отставшую от своей же,
    и следующий круг догнал её скачком. Без порога догоняющий скачок уходил в
    :data:`LAG_JUMP`, а приписанные пять секунд потери оставались навсегда.
    """
    lag = PointerLag()

    done = _run(lag, [(0.0, 100.0), (2.0, 102.0), (9.3, 104.0), (11.3, 111.3), (13.3, 113.3)])

    assert done == []
    assert round(lag.total, 2) == 0.0


def test_a_real_freeze_does_not_hide_behind_the_late_poll_guard() -> None:
    """Настоящая остановка картинки наш круг не удлиняет - и порог её не глушит."""
    lag = PointerLag()

    done = _run(lag, [(0.0, 100.0), (2.0, 102.0), (4.05, 102.0), (6.1, 103.1), (8.1, 105.1)])

    assert len(done) == 1
    assert round(done[0].lost, 2) == 3.0
