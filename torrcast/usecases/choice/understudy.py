"""Дублёр выбранной картины: сосед по франшизе, когда у неё играть нечем."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from torrcast.domain.same_series_later import same_series_later
from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan


def understudy(plans: list[Plan], failed: Plan, args: Args) -> Plan | None:
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
    if failed.want is not None:
        return _episode_understudy(plans, failed, args)
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


def _episode_understudy(plans: list[Plan], failed: Plan, args: Args) -> Plan | None:
    """Дублёр для СЕРИИ: та же вещь под другим именем меню, у которой эта серия есть.

    🔴 TC-1267. «Re:Zero» s2e18: сериал живёт в меню тремя картинами, и паки второго
    сезона лежали под «Re: Жизнь в альтернативном мире с нуля» (оригинал тот же). Тёзкой
    по имени брали самую живую («Re:Zero» 2020, 89 сидов) - а у неё все раздачи своими
    именами сказали «нужной серии нет». Для серии тёзка - картина того же оригинала, и из
    тёзок берётся та, у кого очередь под ЭТУ серию не пуста; живость решает среди них.
    Тёзка другого года - только продолжение счёта сезонов (:func:`same_series_later`):
    карточка «Доктор Кто» 1963 s1e1 уходила к ремейку 2005 и играла его «Розу».
    """
    own, want = _original(failed), failed.want
    if want is None:
        return None
    twins = [
        plan
        for plan in plans
        if plan.picture is not failed.picture
        and plan.picture.kind == failed.picture.kind
        and (
            plan.picture.title.casefold() == failed.picture.title.casefold()
            or (own and _original(plan) == own)
        )
        and same_series_later(plan.picture, failed.picture.year, want.season)
        and plan.candidates(args)
    ]
    return max(twins, key=liveliness, default=None)


def _original(plan: Plan) -> str:
    return " ".join(re.findall(r"\w+", (plan.picture.original or "").casefold()))
