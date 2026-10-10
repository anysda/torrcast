"""Своя строка картины, а не та, которой её открыли (:mod:`web.card`).

Правило отдельным модулем, а не строкой внутри :mod:`web.card`: спрашивают его те же
двое, что и :func:`web.card_lookup.card_lookup` - сама карточка и её тесты. Строка
поиска в адресе карточки - это то, ЧЕМ плитку открыли, а не имя картины: набор мог
остаться недописанным (владелец, TC-1334: «призрак-в-доспехах-202» вместо «...-2026»),
F5 повторяет её же после того, как круг уже ответил пусто, а родня и история заводят
карточку строкой ЧУЖОЙ картины вовсе. :func:`own_plan` пробует по очереди строку из
адреса, собственное имя картины (``title`` того же запроса) и, на самый безнадёжный
случай прямой ссылки без фактов, имя, восстановленное из ключа - и останавливается на
первом круге, где картина СВОЯ, а не просто на первом непустом.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.select.plan import Plan
from web.card_lookup import card_lookup
from web.key_name import key_name
from web.route_year import route_year

#: Круг раздач по одной строке; в бою это :meth:`web.warm_cache.WarmCache.take`.
Circle = Callable[[str], "list[Plan]"]
#: Круг, уже пришедший из сети, без похода туда; в бою :meth:`web.warm_cache.WarmCache.live`.
Warm = Callable[[str], "list[Plan] | None"]


def _cold(_query: str) -> list[Plan] | None:
    return None


def own_plan(
    key: str, query: str, title: str, circle: Circle, warm: Warm = _cold, year: str | None = None
) -> tuple[Plan | None, int, str]:
    """Картина по своему имени, а не по строке, которой её нашли; строка, что сработала.

    Отказ круга ПРО СТРОКУ дорогу следующей не закрывает, и немой он или названный -
    дела не меняет: и «ничего не нашлось», и «во франшизе столько частей нет», и «ничего
    не разобралось», и «раздач с сезоном 9 нет» сказаны про конкретный текст, а не про
    картину, а текст этот карточке принесла родня, история или недописанный набор. Отказ
    инфраструктуры (:class:`~torrcast.domain.infra_error.InfraError`: Prowlarr не
    настроен, лёг TorrServer) - другое дело: он общий на все три попытки и уходит наверх
    сразу, переспрашивать им нечего. Наверх идёт отказ ПОСЛЕДНЕГО довода: зритель читает
    слова про картину, которую открывал, а не про чужую строку.

    Сначала - согретый круг любой из строк, где картина своя (``warm``): история несёт
    строку слагом («рататуй»), круг согрет под «Рататуй», и сетевой круг по слагу стоил
    карточке и «Играть» с закладки 7-8 с.
    """
    known_year = route_year(year or "")
    dated = (
        f"{title.strip()} {known_year}" if key.startswith("movie:") and title and known_year else ""
    )
    candidates = [
        c for c in dict.fromkeys((dated, query.strip(), title.strip(), key_name(key))) if c
    ]
    for candidate in candidates:
        plan, pick = card_lookup(warm(candidate) or [], key)
        if plan is not None:
            return plan, pick, candidate
    failure: NotFoundError | None = None
    for candidate in candidates:
        try:
            plans = circle(candidate)
        except NotFoundError as nothing:
            failure = nothing
            continue
        plan, pick = card_lookup(plans, key)
        if plan is not None:
            return plan, pick, candidate
    if failure is not None:
        raise failure
    return None, 0, ""


__all__ = ["Circle", "Warm", "own_plan"]
