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
    assert closed[0]["why"] == "следом пришла ещё одна перемотка"
