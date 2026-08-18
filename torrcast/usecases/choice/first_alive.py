"""Номер картины по умолчанию: первая по хронологии, чей рой жив."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.backed import backed
from torrcast.usecases.choice.liveliest import liveliest
from torrcast.usecases.choice.liveliness import liveliness
from torrcast.usecases.choice.playable import playable

if TYPE_CHECKING:
    from torrcast.ports.choice_types import _Plan


def first_alive(plans: list[_Plan]) -> int:
    """Номер (с единицы) картины по умолчанию: **первая по хронологии, чей рой жив**.

    Смотреть франшизу начинают с начала, а не с самой обсиженной части: «тачки» — это
    просьба про «Тачки» 2006, даже когда сидов больше у «Тачек 3». Прежний дефолт
    (:func:`liveliest`) на этом и ошибался — печатал `[4]`.

    Мёртвые части при этом пропускаются, иначе Enter снова упирался бы в пустой рой:
    у «моаны» первой в хронологии стоит «Моана: романтика золотого века» 1926 года,
    немая документалка одним VHS-рипом на 5 сидов.

    Живость - **свой рой картины** (:data:`ALIVE_SEEDERS`), а не доля от самой живой
    части франшизы. Доля тут была прямой ошибкой, и стоила она классики: одна свежая
    часть с большим роем объявляла мёртвой всю остальную франшизу. Замер по живой
    выдаче: «мумия» - свежая часть 2026 года набирает сотни сидов, «Мумия» 1999 года
    при живых десятках не дотягивала до четверти от неё и пропускалась, и дефолтом
    десять прогонов из десяти вставала картина, которой человек не называл. То же
    у «хищника», «голодных игр», «дюны», «безумного макса» и «джуманджи».

    * «тачки» - 66 / 0 / 1 / 121 сид: первая часть жива своим роем и выигрывает,
      а мимо проходят «Мультачки» (одни DVD-образы, играть нечем) и «Тачки 2»,
      у которых годным верхом остался 0.4-гигабайтный HDRip «фильм о фильме» на 1 сид;
    * «моана» - 0 / 222 / 140: документалка 1926 года пропускается (годного нет вовсе),
      дефолтом становится «Моана» 2016.

    Тип, названный запросом, весит больше одноимённого соседа другого типа
    (:func:`asked_kind`): «хорошая жена s1e1» — это просьба про сериал, и дефолт
    считается среди сериалов, даже если полнометражная тёзка живее.

    Живого нет вовсе — отдаём самую живую из картин названного типа: выбирать всё
    равно не из чего, но цифра в скобках обязана на что-то указывать.
    """
    return _first_alive(plans, asked_kind(plans))


def _first_alive(plans: list[_Plan], numbers: list[int]) -> int:
    """:func:`first_alive` среди перечисленных номеров - остальные картины не в счёт."""
    if not numbers:
        return liveliest(plans)
    if alive := alive_numbers(plans, numbers):
        return backed(plans, playable(plans, alive))[0]
    return max(numbers, key=lambda n: (liveliness(plans[n - 1]), -n))
