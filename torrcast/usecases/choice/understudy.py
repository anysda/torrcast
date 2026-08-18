"""Дублёр выбранной картины: сосед по франшизе, когда у неё играть нечем."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def understudy(plans: list[Plan], failed: Plan) -> Plan | None:
    """🔴 TC-203. Живая ТЁЗКА выбранной картины - та, которой показ доиграет вместо неё.

    У выбранной картины кончились все раздачи, а рядом в меню стоит одноимённая живая -
    и человек читал отказ. Замер каталога: 6 отказов из 115, и самый наглядный -
    «Человек-невидимка»: дефолт садился на 1933 год (формально живой, играть нечем) при
    живой картине 2020 года в том же меню. Отказ там был честен про картину и неправдой
    про вечер: кино с этим именем в каталоге есть, и оно играет.

    Тёзка - это ровно ТО ЖЕ НАЗВАНИЕ (:func:`_namesake`), а не соседка по франшизе.
    Разница принципиальная: «Тачки 2» вместо «Тачек» - это другое кино, и уходить туда
    самому нельзя ни при каком отказе (о таких соседях говорит подсказка
    :func:`kin_line`, и она остаётся подсказкой). А «Человек-невидимка» 1933 и 2020 -
    это одна вещь, снятая дважды: имя человек назвал верно, промахнулись мы годом.

    Тип тоже обязан совпасть: полнометражка и одноимённый сериал - разные вещи, и
    подменять одно другим молча нельзя ровно по той же причине, по какой этого не делает
    дефолт (:func:`backed`).

    Круг ровно один: берём самую живую из тёзок. Лишний заход стоит человеку секунд, и
    платить их за перебор всего меню незачем - если и она не сыграет, честный отказ
    честнее долгого перебора.
    """
    number = next((n for n, plan in enumerate(plans, start=1) if plan.picture is failed.picture), 0)
    if number == 0:
        return None
    twins = [
        n
        for n in alive_numbers(plans, list(range(1, len(plans) + 1)))
        if n != number
        and _namesake(plans, n, number)
        and plans[n - 1].picture.kind == failed.picture.kind
    ]
    if not twins:
        return None
    return plans[max(twins, key=lambda n: liveliness(plans[n - 1])) - 1]
