"""Какая картина круга отвечает на ключ карточки и каким номером её звать.

Правило отдельным модулем, а не строкой внутри :mod:`web.card`: спрашивают его двое -
сама карточка и её тесты, - а сходится в нём то, что расходится в продукте, имя картины
у ленты раздач и имя у поиска.
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.picture import Picture
from torrcast.domain.picture_names import picture_names
from torrcast.usecases.select.plan import Plan


def card_lookup(plans: list[Plan], key: str) -> tuple[Plan | None, int]:
    """Картина круга по ключу и её номер в нём; ключ ничей - ``(None, 0)``.

    🔴 Картина отвечает на ключ, собранный из ЛЮБОГО её имени. Имён у неё три, и все три
    расходятся: плитка полки зовёт картину так, как её назвала лента раздач («Better
    Days»), круг - прокатным именем каталога («Лучшие дни»), а оригинал у неё третий
    («Shao nian de ni»). Ключ полки не находился в круге НИ РАЗУ, и плитка «Новинок»
    открывала пустую карточку с одной кнопкой «Назад» - из неё нельзя было даже уйти
    стрелками, потому что фокусу больше не на что встать (замер на стенде `.104`
    07-09-2026: ``GET /api/card/movie:better-days:2019`` -> 404 ``not_found``, пункт 11
    приёмки красный после 12 нажатий по скелету).

    Догадки тут нет: ключ каждого имени собирается тем же правилом :attr:`Picture.key`, а
    не разбором строки, и род с годом в нём те же. Тёзка в другом году остаётся отдельной
    картиной - «Лучшие дни» 2025 несёт тот же алиас ``better-days``, но на ключ
    ``movie:better-days:2019`` не отвечает.
    """
    for number, plan in enumerate(plans, start=1):
        if key in _keys(plan.picture):
            return plan, number
    return None, 0


def _keys(picture: Picture) -> set[str]:
    """Ключи одной картины по всем её именам - тем же правилом :attr:`Picture.key`."""
    return {replace(picture, title=name).key for name in picture_names(picture)}


__all__ = ["card_lookup"]
