"""Зеркало остановки: она доходит и до идущего подъёма, и до пустого экрана."""

from __future__ import annotations

from collections.abc import Sequence

from hass.orders import Orders
from hass.stopping import STOP, stopping
from tests.fakes.playback_session import FakePlaybackSession


def _recording(asked: list[list[str]]) -> Orders:
    """Поручения с командой, которая только запоминает, чем её позвали."""

    def command(argv: Sequence[str] | None) -> int:
        asked.append(list(argv or []))
        return 0

    return Orders(command)


def test_the_stop_reaches_the_running_raise_and_the_queue_behind_it() -> None:
    """Пока подъём идёт, остановка кладёт ОТДЕЛЬНЫЙ факт и не ждёт очереди.

    Очередь занята подъёмом, и поручение остановки дождалось бы конца его бюджета
    старта - все эти секунды человек смотрел бы на показ, от которого уже отказался
    (замер 03-09-2026: 358 с). Поэтому отказ читает сам подъём, а юнит гасится сразу.
    """
    asked: list[list[str]] = []
    orders = _recording(asked)
    session = FakePlaybackSession(playing=True)
    assert orders.take(["матрица"]), "подъём не встал в работу - мерить дальше нечего"

    stopping(orders, session)

    assert orders.abandoned(), "идущий подъём не узнал, что от него отказались"
    assert session.stopped == 1, "поднявшийся показ остался на экране после остановки"
    orders.run_one()
    orders.run_one()
    assert asked == [["матрица"], [STOP]], f"остановка не доехала до продукта: {asked}"


def test_a_stop_on_an_empty_screen_is_taken_too_and_touches_no_unit() -> None:
    """Гасить нечего - отказывать всё равно нечем: продукт просят остановиться и так.

    Юнита при этом никто не трогает: снимать нечего, и `abandon` честно говорит, что
    подъёма не было.
    """
    asked: list[list[str]] = []
    orders = _recording(asked)
    session = FakePlaybackSession()

    stopping(orders, session)

    assert not orders.abandoned(), "снятым назван подъём, которого не было"
    assert session.stopped == 0, "гасить было нечего, а юнит всё равно тронули"
    orders.run_one()
    assert asked == [[STOP]], f"остановка на пустом экране не доехала до продукта: {asked}"
