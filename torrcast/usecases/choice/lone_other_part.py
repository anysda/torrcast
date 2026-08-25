"""Отказ вместо показа, когда единственная найденная картина - другая часть франшизы."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def lone_other_part(plans: list[Plan], asked: str) -> str:
    """Отказ вместо показа, когда нашлась ОДНА картина и она - не спрошенная часть.

    🔴 TC-814. Спросили «лёд» - это просьба про первую часть, а в выдаче одна картина,
    и это «Лёд 3» 2024 года. Меню при одной картине не задаётся вовсе, поэтому страж
    перескока (:func:`part_one_swap`) до этого случая не доходит: ему нужны хотя бы два
    пункта, чтобы было из чего выбирать. Выходило худшее - показ начинался молча, и
    вместо спрошенного зритель получал другое кино той же франшизы.

    Просили одну часть - другую не подставляем: строка называет, что первой части в
    выдаче нет, что нашлось вместо неё и каким запросом это спросить. Выбирать тут не
    из чего, поэтому вопроса нет, а есть отказ.

    Пустой ответ - брать найденное честно, и случаев тут три:

    * номер назван явно («лёд 3») - спрошенное и нашлось;
    * картина не номерована («Оппенгеймер», «Довод») - номера части у неё нет, и
      подменять было нечем;
    * нашлась сама первая часть либо картина чужой франшизы - имя запроса до её
      линейки не относится вовсе.

    Замер по сохранённым выдачам, 100 запросов: одна картина в меню у 28, строка встаёт
    ровно на одном - «лёд». Остальные 27 либо назвали номер сами («форсаж 5»,
    «терминатор 2»), либо номерованной части не имеют.
    """
    if len(plans) != 1:
        return ""
    name, index = split_franchise_index(asked)
    if index is not None:
        return ""
    picture = plans[0].picture
    if picture.kind == "other" or picture.part in (None, 1):
        return ""
    key = slugify(name)
    names = {picture.franchise}
    if picture.original:
        names |= {franchise_key(picture.original)}
    if not key or key not in names:
        return ""
    return (
        f"«{name}»: первой части в выдаче нет, и другую часть сам не включаю - "
        f"есть «{_named(picture)}», спроси её номером «{name} {picture.part}»"
    )
