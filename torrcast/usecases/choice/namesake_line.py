"""Честная строка про тёзку, взятую без вопроса: какая, сколько ещё и где варианты."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def namesake_line(plans: list[Plan], taken: int, asked: str) -> str:
    """🔴 TC-812. Честная строка взятия самой живой тёзки: какая взята, сколько есть ещё.

    Подмена перестала быть молчаливой - значит вся защита здесь, и строка обязана быть
    точной: называет взятую картину годом, говорит, сколько под этим именем есть ЕЩЁ
    (других картин, а не частей - у частей своё правило), и называет ход к ним -
    ``--menu``, за которым стоят варианты. Число сидов названо, потому что «самая живая»
    без числа была бы просьбой поверить на слово.
    """
    others = [n for n in asked_kind(plans) if n != taken and _namesake(plans, n, taken)]
    plan = plans[taken - 1]
    return (
        f"беру «{_named(plan.picture)}» - самая живая из одноимённых, у лучшей её "
        f"раздачи сидов {liveliness(plan)}; других картин под этим именем: "
        f"{len(others)}, их список: cast {asked} --menu"
    )
