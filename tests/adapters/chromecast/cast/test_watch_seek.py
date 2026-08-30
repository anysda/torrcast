"""Сторож перемотки: конец ожидания - сдвиг указателя, а не слово ``PLAYING``."""

from __future__ import annotations

from typing import Any

from tests.adapters.chromecast.cast.wired import Wired
from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.cast.watch_seek import _watch_seek


def _seeks(tape: Tape) -> list[dict[str, Any]]:
    return tape.named("seek")


def test_the_wait_is_measured_to_the_picture_and_not_to_the_word_playing(
    tape: Tape,
) -> None:
    """Приёмник говорит ``PLAYING`` РАНЬШЕ первого кадра.

    Метрика, верившая слову, писала в ленту 0.0 с у всех трёх прыжков подряд - при том
    что картинка возвращалась за 6.0, 5.9 и 9.9 с. Указатель после перемотки стоит на
    месте приземления, пока приёмник не наберёт буфер, и трогается ровно с кадром.
    """
    clock = FakeClock(now=10.0)
    receiver = Wired(clock=clock)

    _watch_seek(receiver, 100.0, "PLAYING")  # обычный ход показа
    _watch_seek(receiver, 900.0, "PLAYING")  # прыжок: перемотка замечена
    assert _seeks(tape) == [], "картинки ещё не было - записи тоже"

    clock.now += 6.0
    _watch_seek(receiver, 900.0, "PLAYING")  # указатель стоит: кадра нет
    assert _seeks(tape) == []

    _watch_seek(receiver, 900.0 + receiver.PICTURE_STEP, "PLAYING")

    (rec,) = _seeks(tape)
    assert rec["frm"] == 100.0
    assert rec["to"] == 900.0
    assert rec["wait"] == 6.0


def test_the_watchdogs_own_jump_is_not_counted_as_a_seek(
    tape: Tape,
) -> None:
    """Сторож только что назвал это место сам - перемоткой человека это не считается."""
    receiver = Wired()
    receiver._nudged_to = 900.0

    _watch_seek(receiver, 100.0, "BUFFERING")
    _watch_seek(receiver, 900.0, "BUFFERING")

    assert _seeks(tape) == []
    assert receiver._nudged_to == -1.0, "на второй прыжок нужен и второй нудж"


def test_a_dead_session_is_not_a_rewind_to_the_beginning(
    tape: Tape,
) -> None:
    """У мёртвой сессии позиции нет вовсе, и её ноль - не перемотка в начало.

    Прими сторож этот ноль за перемотку - сравнивать в следующий раз он стал бы с
    нулём, а повтор LOAD вернул бы человека к началу фильма.
    """
    receiver = Wired()
    _watch_seek(receiver, 500.0, "PLAYING")

    _watch_seek(receiver, 0.0, "IDLE")

    assert receiver._seen == 500.0, "позиции не было - сравнивать не с чем"
    assert _seeks(tape) == []


def test_a_second_seek_in_a_row_closes_the_first_one_with_a_record(
    tape: Tape,
) -> None:
    """Человек мотает второй раз - первая перемотка кончилась ничем, и это записано."""
    receiver = Wired()
    _watch_seek(receiver, 100.0, "PLAYING")
    _watch_seek(receiver, 900.0, "PLAYING")

    _watch_seek(receiver, 2000.0, "PLAYING")

    closed = _seeks(tape)
    assert [rec["wait"] for rec in closed] == [None]
    assert closed[0]["why"] == "another seek arrived right after"


def test_a_stalled_poll_circle_does_not_turn_playback_into_a_seek(
    tape: Tape,
) -> None:
    """Круг опроса задержался - плёнка за это время уехала честно, и это не перемотка.

    Порог стоял на прыжке целиком и молча описывал опрос раз в 2 с. Круг своё расписание
    держит не всегда (подъём оборванной упаковки, повтор ``LOAD``, медленный ответ
    приёмника), и каждая задержка дольше порога писала в ленту перемотку, которой не было.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)

    _watch_seek(receiver, 500.0, "PLAYING")
    clock.now += 60.0  # круг опроса простоял минуту
    _watch_seek(receiver, 555.0, "PLAYING")  # показ всё это время играл
    clock.now += 2.0
    _watch_seek(receiver, 557.0, "PLAYING")

    assert _seeks(tape) == [], "перемотки не было - показ просто играл"


def test_a_real_seek_is_still_caught_when_the_circle_kept_its_pace(
    tape: Tape,
) -> None:
    """Задержки не было - и прыжок вперёд по-прежнему перемотка, а не ход показа."""
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)

    _watch_seek(receiver, 500.0, "PLAYING")
    clock.now += 2.0
    _watch_seek(receiver, 900.0, "PLAYING")
    clock.now += 2.0
    _watch_seek(receiver, 900.0 + receiver.PICTURE_STEP, "PLAYING")

    (rec,) = _seeks(tape)
    assert (rec["frm"], rec["to"]) == (500.0, 900.0)


def test_time_between_polls_buys_nothing_to_a_jump_backwards(
    tape: Tape,
) -> None:
    """Назад показ не уходит, сколько бы времени ни прошло: откат - всегда перемотка."""
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)

    _watch_seek(receiver, 1000.0, "PLAYING")
    clock.now += 60.0
    _watch_seek(receiver, 500.0, "PLAYING")
    clock.now += 2.0
    _watch_seek(receiver, 500.0 + receiver.PICTURE_STEP, "PLAYING")

    (rec,) = _seeks(tape)
    assert (rec["frm"], rec["to"]) == (1000.0, 500.0)


def test_a_missed_nudge_mark_does_not_swallow_the_next_human_seek(
    tape: Tape,
) -> None:
    """Метка нуджа описывает ОДИН наш прыжок, а не место фильма до конца показа.

    Приёмник прыгнул мимо названного сторожем места - метка оставалась взведённой, и
    следующая перемотка человека, приземлившаяся рядом с ней, в ленту не попадала вовсе.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)
    receiver._nudged_to = 900.0

    _watch_seek(receiver, 300.0, "PLAYING")
    clock.now += 2.0
    _watch_seek(receiver, 500.0, "PLAYING")  # приёмник прыгнул не туда, куда звали
    clock.now += 2.0
    _watch_seek(receiver, 895.0, "PLAYING")  # а вот это уже человек
    clock.now += 2.0
    _watch_seek(receiver, 895.0 + receiver.PICTURE_STEP, "PLAYING")

    assert [(rec["frm"], rec["to"]) for rec in _seeks(tape)] == [
        (300.0, 500.0),
        (500.0, 895.0),
    ], "перемотка человека рядом со старой меткой нуджа обязана быть в ленте"


def test_the_allowance_is_the_larger_of_the_two_and_never_their_sum(
    tape: Tape,
) -> None:
    """Настоящие перемотки лежат к порогу вплотную, и складывать запасы нельзя.

    Замер по ленте живого сеанса (19 перемоток руками): сложи жёсткий запас с плёнкой
    между опросами - и порог на ровном круге поднимется с 15.0 до 17.0 с, а вместе с ним
    из ленты уйдут три настоящие перемотки, чьи прыжки в этот зазор и попадают.
    """
    clock = FakeClock(now=100.0)
    receiver = Wired(clock=clock)

    _watch_seek(receiver, 500.0, "PLAYING")
    clock.now += 2.0  # круг пришёл вовремя
    _watch_seek(receiver, 515.8, "PLAYING")  # прыжок чуть выше жёсткого запаса
    clock.now += 2.0
    _watch_seek(receiver, 515.8 + receiver.PICTURE_STEP, "PLAYING")

    (rec,) = _seeks(tape)
    assert (rec["frm"], rec["to"]) == (500.0, 515.8)
