"""Зеркало поручений моста: подъём идёт по одному, а остановка не спрашивает очереди."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hass.orders import Orders

if TYPE_CHECKING:
    from collections.abc import Sequence


def _nothing(_argv: Sequence[str] | None) -> int:
    return 0


def test_a_second_raise_is_refused_while_the_first_one_is_underway() -> None:
    orders = Orders(_nothing)

    assert orders.take(["матрица"]), "первый подъём обязан взяться"
    assert not orders.take(["муха"]), "второй подъём взялся поверх идущего"
    assert orders.underway()

    assert orders.run_one()
    assert not orders.underway()
    assert orders.take(["муха"]), "кончился первый - второй берётся"


def test_a_forced_order_never_waits_for_its_turn() -> None:
    """Остановке отказать нечем: она встаёт в очередь, не спрашивая занятости."""
    orders = Orders(_nothing)

    orders.take(["матрица"])
    orders.force(["stop"])
    assert orders.run_one() and orders.run_one(), "оба поручения обязаны быть в очереди"


def test_the_raise_underway_learns_that_the_person_called_it_off() -> None:
    """🔴 TC-1022. До идущего подъёма очередь не дойдёт - отказ кладётся фактом.

    Живой замер 03-09-2026: остановку приняли за 0,00 с, а продукт пришёл в ``idle``
    через 358 с - поручение остановки досиживало в очереди весь бюджет старта чужого
    подъёма. Спрашивает этот факт сам подъём, пока он ещё идёт.
    """
    seen: list[bool] = []

    def command(_argv: Sequence[str] | None) -> int:
        seen.append(orders.abandoned())  # ровно то, что спрашивает запуск показа
        return 0

    orders = Orders(command)

    assert not orders.abandon(), "подъёма не было, а поручению сказали, что был"
    orders.take(["матрица"])
    assert orders.abandon(), "отказ не узнал про идущий подъём"
    assert orders.run_one()

    assert seen == [True], "подъём не узнал, что от него отказались"


def test_a_new_show_does_not_inherit_the_refusal_of_the_previous_one() -> None:
    """Отказ был от ПРОШЛОГО заказа: следующий подъём начинается с чистого листа."""
    seen: list[bool] = []

    def command(_argv: Sequence[str] | None) -> int:
        seen.append(orders.abandoned())
        return 0

    orders = Orders(command)

    orders.take(["матрица"])
    orders.abandon()
    assert orders.run_one()

    orders.take(["муха"])
    assert orders.run_one()

    assert seen == [True, False], f"отказ пережил начало следующего показа: {seen}"


def test_a_show_the_person_called_off_leaves_no_complaint_behind() -> None:
    """Снятый заказ - не отказ продукта: жаловаться человеку на его же просьбу не за что.

    Отмена в консоль не пишет ни строки, поэтому «словом отказа» стал бы голый код
    возврата - число на карточке вместо человеческой причины.
    """

    def cancelled(_argv: Sequence[str] | None) -> int:
        return 3  # молча, как это делает отмена

    orders = Orders(cancelled)

    orders.take(["матрица"])
    orders.abandon()
    assert orders.run_one()

    assert orders.last_error == "", f"человеку сказали «{orders.last_error}» про его же отказ"


def test_the_refusal_of_a_command_is_remembered_in_the_words_the_console_said() -> None:
    said = ["ничего не нашлось по запросу «муха»"]

    def command(_argv: Sequence[str] | None) -> int:
        if said:
            print(said.pop())
            return 1
        return 0

    orders = Orders(command)

    orders.take(["муха"])
    orders.run_one()
    assert orders.last_error == "ничего не нашлось по запросу «муха»"

    orders.take(["матрица"])
    assert orders.last_error == "", "прошлый отказ пережил начало следующего показа"


def test_the_loop_leaves_when_it_is_asked_to() -> None:
    orders = Orders(_nothing)

    orders.leave()
    assert not orders.run_one()
