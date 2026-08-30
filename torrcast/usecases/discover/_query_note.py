"""Строка о том, что запрос второго захода выбрала справка, а не транслит с выдачей."""

from __future__ import annotations

from torrcast.domain.alt_query import alt_query
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.facts.origin import Origin
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify


def _query_note(name: str, alt: str, pool: list[Release], about: Origin) -> str:
    """Строка о том, что запрос второго захода выбрала справка, а не транслит с выдачей.

    Молчаливых подмен у нас нет, и смена ЗАПРОСА - такая же подмена, как смена картины:
    в индексер уходит не то, что человек набрал. Пока справка молчала, второй заход шёл
    транслитом («Крики и шёпот» → ``kriki i shepot``), и по одной строке фазы «поиск
    «Viskningar och rop»» не понять, откуда взялось шведское имя и почему ему верить.

    Печатается только там, где справка ДЕЙСТВИТЕЛЬНО изменила запрос: без неё второй заход
    ушёл бы другим именем (транслитом или оригиналом из выдачи). Совпали - говорить не о
    чем, и строки нет: справка тут ничего не решила.
    """
    if not alt or not about.title:
        return ""
    blind = alt_query(name, pool)  # чем бы искали, не будь справки
    if not blind:
        return phrase("discover.origin_would_be_blind", alt=alt)
    if slugify(blind) == slugify(alt):
        return ""
    return phrase("discover.origin_instead_of_blind", alt=alt, blind=blind)
