"""Номер самой живой тёзки дефолта по году; 0 - тёзок у дефолта нет."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.of_asked_year import of_asked_year
from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.liveliness import liveliness
from torrcast.usecases.choice.renowned_work import renowned_work

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def namesake_take(plans: list[Plan], asked: str = "") -> int:
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

    🔴 TC-1398. Год, названный запросом, и есть ответ «которую из тёзок»: «Призрак в
    доспехах 2026» человек берёт из нашего же меню, и фильм 1995 года, оказавшийся в этом
    круге живее, был бы подменой. Живая тёзка названного года берётся первой; мёртвая
    или отсутствующая - самая живая, как прежде.

    Без года живость решает только среди версий одной работы (:func:`renowned_work`):
    карта IMDb называет самую известную из доказанных работ, и рой чужой работы под тем же
    русским именем её не подменяет. Карта молчит обо всех - решает живость, как прежде.
    """
    default = first_alive(plans)
    numbers = asked_kind(plans)
    twins = [n for n in numbers if n != default and _namesake(plans, n, default)]
    if not twins:
        return 0
    pool = [default, *twins]
    named = {id(p) for p in of_asked_year([plans[n - 1].picture for n in pool], asked)}
    pool = alive_numbers(plans, [n for n in pool if id(plans[n - 1].picture) in named]) or pool
    pool = renowned_work(plans, pool)
    return max(pool, key=lambda n: (liveliness(plans[n - 1]), -n))
