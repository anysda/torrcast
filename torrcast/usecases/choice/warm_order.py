"""Порядок прогрева под меню: греется голова очереди, а не верх ранжира."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.ports.choice_types import _Plan


def warm_order(plans: list[_Plan]) -> list[_Plan]:
    """Кого греть под меню: сверху вниз, в том же порядке, который видит человек."""
    return plans
