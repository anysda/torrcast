"""Номер самой живой картины меню."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.ports.choice_types import _Plan


def liveliest(plans: list[_Plan]) -> int:
    """Номер (с единицы) самой живой картины — он же дефолт меню и первый на прогрев.

    Список остаётся хронологическим, меняется только цифра в скобках:
    «моана» печатает четыре картины и предлагает вторую, а не немую документалку
    1926 года. Равный вес — берём раннюю: при ничьей хронология и есть ответ.
    """
    return max(range(1, len(plans) + 1), key=lambda n: (liveliness(plans[n - 1]), -n))
