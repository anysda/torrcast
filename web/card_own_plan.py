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

from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.usecases.select.plan import Plan
from web.card_lookup import card_lookup

#: Круг раздач по одной строке; в бою это :meth:`web.warm_cache.WarmCache.take`.
Circle = Callable[[str], "list[Plan]"]


def own_plan(key: str, query: str, title: str, circle: Circle) -> tuple[Plan | None, int, str]:
    """Картина по своему имени, а не по строке, которой её нашли; строка, что сработала.

    «Ничего не нашлось» (:class:`NothingFoundError`) одной строки не закрывает дорогу
    следующей: круг честно ответил пусто на конкретный текст, а не на картину. Именной
    же отказ круга (Prowlarr не настроен и т.п.) общий на все три попытки и уходит
    наверх сразу - переспрашивать им нечего.
    """
    tried: set[str] = set()
    failure: NothingFoundError | None = None
    for candidate in (query.strip(), title.strip(), _key_name(key)):
        if not candidate or candidate in tried:
            continue
        tried.add(candidate)
        try:
            plans = circle(candidate)
        except NothingFoundError as nothing:
            failure = nothing
            continue
        plan, pick = card_lookup(plans, key)
        if plan is not None:
            return plan, pick, candidate
    if failure is not None:
        raise failure
    return None, 0, ""


def _key_name(key: str) -> str:
    """Имя картины из ключа: последний довод, когда её собственное имя не пришло вовсе."""
    _, _, tail = key.partition(":")
    slug, _, _ = tail.rpartition(":")
    return slug.replace("-", " ")


__all__ = ["Circle", "own_plan"]
