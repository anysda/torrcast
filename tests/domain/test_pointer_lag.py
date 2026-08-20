"""Зеркало правила подгруза: подгруз доказывает ход указателя, а не слово приёмника."""

from __future__ import annotations

from itertools import pairwise

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


def test_a_catching_up_pointer_never_buys_the_viewer_any_film() -> None:
    """🔴 Догоняющий скачок уменьшать накопленный счёт не имеет права.

    Приёмник публикует позицию своей сеткой, и снятый с неё указатель то отстаёт от часов
    (наш круг растянулся, сетка не сдвинулась), то догоняет их скачком (устаревший снимок
    сменился свежим). Отставание правило выбрасывает вместе с длинным кругом
    (:data:`LAG_LATE`), а догоняющий скачок короче :data:`LAG_JUMP` остаётся принятым - и
    накопленное знаковой суммой число уезжало в минус на этой однобокой паре. Плёнки
    зритель тут не терял вовсе: показ идёт вровень с часами, а сетка - вся разница.
    """
    grid, at, ticks = 2.03, 0.0, []
    for k in range(300):
        at += 2.7 if k % 3 == 0 else 2.0  # каждый третий круг растягивается сверх LAG_LATE
        ticks.append((at, 100.0 + grid * int(at / grid)))
    lag = PointerLag()

    done, trail = [], []
    for now, pos in ticks:
        if (found := lag.see(pos, now)) is not None:
            done.append(found)
        trail.append(lag.total)

    assert done == [], "ровный показ через сетку приёмника подгрузом не является"
    assert all(b >= a for a, b in pairwise(trail)), "опережение указателя отняло плёнку"
    assert round(lag.total, 2) == 0.0


def _grid_walk(
    grid: float, step: float, secs: float, stall: tuple[float, float] = (0.0, 0.0)
) -> list[tuple[float, float]]:
    """Опросы шагом ``step`` по приёмнику, публикующему место своей сеткой ``grid``.

    Плёнка идёт вровень с часами всюду, кроме ``stall`` - там картинка стоит.
    """
    began, held = stall
    ticks, at = [], 0.0
    while at < secs:
        tick = grid * int(at / grid)
        film = tick if tick < began else max(began, tick - held)
        ticks.append((at, 100.0 + film))
        at += step
    return ticks


def test_a_stale_snapshot_is_not_a_stall_at_any_poll_step() -> None:
    """🔴 Правило не имеет права зависеть от НАШЕГО шага опроса.

    Приёмник обновляет место не тогда, когда его спросили, а своей сеткой, и круг, на
    который свежий снимок не пришёлся, отдаёт ровно то же число. Пока наш круг длиннее
    сетки, таких кругов почти нет, и правило честно по совпадению. Замер на ленте
    двухчасового показа: та же лента, разложенная на ровный шаг 2.0 с при сетке приёмника
    2.03 с, дала 179 подгрузов вместо четырёх и накопленный счёт +415 с при дефиците
    16.35 с. Шаг опроса - наша величина, в окне старта он уже 0.5 с.
    """
    for grid in (1.0, 2.03, 3.0):
        for step in (0.5, 1.0, 1.5, 2.0, grid, 2.118, 4.0):
            lag = PointerLag()

            done = _run(lag, _grid_walk(grid, step, 600.0))

            assert done == [], f"сетка {grid}, шаг {step}: подгруз там, где зритель не терял"
            assert round(lag.total, 2) == 0.0, f"сетка {grid}, шаг {step}: долг из ничего"


def test_a_stall_is_seen_even_when_we_ask_faster_than_the_receiver_answers() -> None:
    """Остановка не пропадает оттого, что мы спрашиваем чаще, чем приёмник отвечает.

    Плоский круг и остановка выглядят одинаково - неподвижным указателем; отличает их
    то, сколько указатель простоял против шага, которым потом сдвинулся. Шесть секунд
    стоящей картинки длиннее любой сетки, и правило обязано их увидеть на любом шаге.
    """
    for grid, step in ((2.03, 0.5), (2.03, 2.0), (2.03, 2.118), (1.0, 1.5)):
        lag = PointerLag()

        done = _run(lag, _grid_walk(grid, step, 240.0, stall=(100.0, 6.0)))

        assert done, f"сетка {grid}, шаг {step}: шесть секунд стоящей картинки потеряны"
        assert 5.0 <= lag.total <= 7.0, f"сетка {grid}, шаг {step}: насчитано {lag.total}"
