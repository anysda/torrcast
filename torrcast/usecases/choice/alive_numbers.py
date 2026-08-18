"""Номера картин, у которых есть чем играть."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.usecases.select._plan import _Plan


def alive_numbers(plans: list[_Plan], numbers: list[int]) -> list[int]:
    """Номера картин, у которых есть чем играть; пусто - живых нет вовсе.

    Порог - свой рой картины (:data:`ALIVE_SEEDERS`), см. :func:`first_alive`. Соседи по
    франшизе в этот вопрос не входят вовсе: «есть чем играть» - свойство самой картины,
    и чужой рой его ни подтвердить, ни отменить не может.
    """
    return [n for n in numbers if liveliness(plans[n - 1]) >= _environment_port().alive_seeders]
