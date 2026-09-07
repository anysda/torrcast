"""Какая картина круга отвечает на ключ карточки и каким номером её звать.

Правило отдельным модулем, а не строкой внутри :mod:`web.card`: спрашивают его двое -
сама карточка и её тесты, - а сходится в нём то, что расходится в продукте, имя картины
у ленты раздач и имя у поиска.
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan


def card_lookup(plans: list[Plan], key: str) -> tuple[Plan | None, int]:
    """Картина круга по ключу и её номер в нём; ключ ничей - ``(None, 0)``.

    🔴 Картина отвечает и на ключ, собранный из её ОРИГИНАЛЬНОГО имени. Плитка полки
    зовёт картину так, как её назвала лента раздач, а круг - прокатным именем, и ключи у
    одной картины расходятся: лента знает «Bones and All» (2022), а поиск по тому же
    запросу отвечает «Целиком и полностью» с ключом ``movie:целиком-и-полностью:2022``.
    Ключ полки не находился в круге НИ РАЗУ, и каждая плитка «Новинок» и «Популярного»
    открывала пустую карточку с одной кнопкой «Назад» (замер на стенде `.104`
    07-09-2026: ``GET /api/card/movie:bones-and-all:2022`` -> 404 ``not_found``).

    Догадки тут нет: второй ключ собирается тем же правилом :attr:`Picture.key`, а не
    разбором строки, и род с годом в нём те же. Тёзка по имени в другом году остаётся
    отдельной картиной - «Anthony Jeselnik: Bones and All» 2024 даёт свой ключ и не
    совпадёт с нашим.
    """
    for number, plan in enumerate(plans, start=1):
        if plan.picture.key == key or _by_original(plan.picture) == key:
            return plan, number
    return None, 0


def _by_original(picture: Picture) -> str:
    """Ключ той же картины, названной оригинальным именем; имени нет - пустая строка."""
    if not picture.original:
        return ""
    return replace(picture, title=picture.original).key


__all__ = ["card_lookup"]
