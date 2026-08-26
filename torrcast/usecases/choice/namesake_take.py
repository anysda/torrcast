"""Номер самой живой тёзки дефолта по году; 0 - тёзок у дефолта нет."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def namesake_take(plans: list[Plan]) -> int:
    """Номер (с единицы) самой живой из тёзок дефолта по году; 0 - это не случай тёзок.

    🔴 TC-812, решение владельца 26-08-2026: «включать самую живую это показатель того
    что картина популярна а варианты будут уже за --menu». Тёзки - РАЗНЫЕ картины под
    одним именем (обычно разных лет), и вопрос «которую из них» уходит из обычного пути:
    берётся самая живая, и берётся не молча (:func:`namesake_line`).

    Круг взятия - дефолт (:func:`first_alive`) и его тёзки (:func:`_namesake`), и никого
    больше: соседку с ДРУГИМ именем подставлять нельзя, даже если её рой живее - это
    ровно та подмена, которую держит страж имени (:func:`named_elsewhere`). Франшизу
    правило не трогает: дефолт номерованных частей - по-прежнему первая живая, и там
    свой страж (:func:`part_one_swap`), который спрашивается раньше.

    Живейший сам дефолт - возвращается он: взятие перестало быть вопросом, а не сменило
    картину. Ничья читается хронологией, как у :func:`liveliest`.
    """
    default = first_alive(plans)
    numbers = asked_kind(plans)
    twins = [n for n in numbers if n != default and _namesake(plans, n, default)]
    if not twins:
        return 0
    return max([default, *twins], key=lambda n: (liveliness(plans[n - 1]), -n))
