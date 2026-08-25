"""Верх меню заведомо та картина, которую спросили: сказать о нём нечего."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.default_note import default_note
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.named_elsewhere import named_elsewhere
from torrcast.usecases.choice.part_one_swap import part_one_swap

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def certain_default(plans: list[Plan], asked: str) -> bool:
    """Верх меню заведомо та картина, которую спросили, - вопроса тут нет.

    Граница «здесь берём молча, здесь спрашиваем» проходит по тому, есть ли о решении
    честная строка. Все строки про смену картины уже посчитаны и все молчат - значит
    дефолт не перескочил через часть франшизы (:func:`part_one_swap`), не ушёл с картины,
    чьё имя названо целиком (:func:`named_elsewhere`), не сменил тип,
    не пропустил картину выше себя и не имеет тёзки по году (:func:`default_note`).
    Другой картины, которую человек мог иметь в виду, тут просто нет.

    🔴 Первое условие - :func:`first_alive`, и оно не про живость, а про то, о КОМ
    молчат обе строки: дефолт обязан стоять ПЕРВЫМ пунктом списка. Взять молча картину,
    мимо которой дефолт прошёл, - это и есть подмена, которая хуже отказа, поэтому любой
    пропуск возвращает вопрос, а сам пропуск при этом называется строкой.

    Замер по сохранённым выдачам, 99 запросов: меню из двух и больше картин - 71 запрос,
    и на 28 из них вопрос не задаётся вовсе; подмен среди этих 28 нет ни одной.

    Послаблений дальше не будет. «Спросили серию, а это другой тип» звучит невинно -
    человек ведь сам назвал серию, - но на «блич s1e1» за этой строкой стоит переезд с
    «Блича» 2004 года на «Блич: Тысячелетняя кровавая война», то есть ровно подмена.
    """
    return (
        first_alive(plans) == 1
        and not part_one_swap(plans, asked)
        and not named_elsewhere(plans, asked)
        and not default_note(plans, asked)
    )
