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


def test_a_forced_order_never_waits_for_its_turn_and_names_the_raise_it_met() -> None:
    """Остановке отказать нечем: она встаёт в очередь и говорит, шёл ли подъём."""
    orders = Orders(_nothing)

    assert not orders.force(["stop"]), "подъёма не было, а поручению сказали, что был"
    assert orders.run_one()

    orders.take(["матрица"])
    assert orders.force(["stop"]), "поручение не узнало про идущий подъём"


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
