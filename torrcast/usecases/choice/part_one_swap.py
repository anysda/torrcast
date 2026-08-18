"""Честная строка вместо дефолта, когда дефолт подменил бы часть франшизы."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.default_note import _passed_why
from torrcast.usecases.choice.first_alive import first_alive

if TYPE_CHECKING:
    from torrcast.ports.choice_types import _Plan


def part_one_swap(plans: list[_Plan], asked: str) -> str:
    """Честная строка вместо дефолта меню, когда дефолт подменил бы часть франшизы.

    🔴 TC-373. Запрос «тачки» - это просьба про «Тачки» 2006 года, и пока первая часть
    играет, дефолт стоит на ней. А вот когда её нет в выдаче или играть ей нечем, дефолт
    по правилу «первая живая часть» (:func:`first_alive`) перескакивал на «Тачки 2» - и
    Enter включал другое кино той же франшизы, которого не просили. Строка про это была
    (:func:`default_note`), но показ всё равно начинался сам.

    Теперь в этом случае дефолта нет вовсе: строка называет, что случилось с первой
    частью, список того, что есть, уже на экране над ней, и номер части называет сам
    человек. Пустой ответ - дефолт честен, и случаев тут три:

    * номер назван явно («тачки 2») - спрошенное уже отобрано до меню
      (:func:`~torrcast.parse.pick_franchise`), и дефолт - ровно оно;
    * франшиза без номерованных частей («Моана», «Мумия») - там первая ЖИВАЯ картина и
      есть ответ на запрос, решение «дефолт франшизы - первая живая часть» не тронуто;
    * дефолт встал на саму первую часть или на её ТЁЗКУ по году («Человек-невидимка» 2020
      вместо 1933): тёзка - та же вещь под тем же именем, послабление для неё остаётся.

    Запрос, назвавший франшизу оригинальным именем («cars»), читается так же, как русский:
    имя первой части сверяется в обоих языках.

    Линейкой считаются только картины: номерованная книжная серия («Homo Ludens 1» рядом
    со «Сталкером») франшизу не образует. И номер внутри одной картины («Дары Смерти:
    Часть I») - это глава, а не часть франшизы: если «первая часть» линейки младше другой
    картины меню, перед нами семья однофамильцев, и там дефолт честен.
    """
    name, index = split_franchise_index(asked)
    if index is not None or len(plans) < 2:
        return ""
    key = slugify(name)
    pictures = [plan.picture for plan in plans]
    films = [p for p in pictures if p.kind != "other"]
    if not key or not any(p.part is not None for p in films):
        return ""
    line = _numbered_line(films)[0]
    first = line[0] if line and line[0].part in (None, 1) else None
    if first is not None and any(p.year and first.year and p.year < first.year for p in films):
        return ""
    names = {p.franchise for p in pictures}
    # Оригинальные имена зовут ту же франшизу («cars» - это «тачки»), а корень ключа
    # (:func:`franchise_key`) режет номер части: «Cars 2» подписано корнем «cars».
    names |= {franchise_key(p.original) for p in pictures if p.original}
    if key not in names:  # запрос назвал не франшизу, а картину - подменять тут нечего
        return ""
    if first is None:
        return (
            f"«{name}»: первой части в выдаче нет, и вместо неё другую часть сам не "
            f"включаю - вот что есть, назови номер"
        )
    default = plans[first_alive(plans) - 1].picture
    if default is first or default.title.casefold() == first.title.casefold():
        return ""
    number = next(n for n, plan in enumerate(plans, start=1) if plan.picture is first)
    why = _passed_why(plans, number, asked_kind(plans))
    return (
        f"«{_named(first)}» не играет: {why}; вместо неё другую часть сам не включаю - "
        f"вот что есть, назови номер"
    )
