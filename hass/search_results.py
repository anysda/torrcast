"""Список картин по запросу как тело ``POST /api/search``: только форма, не поиск.

Поиск делает :func:`torrcast.usecases.discover.search_circle.search_circle`
(:meth:`hass.bridge.Bridge.search`); здесь - его выдача, пронумерованная под флаг
``--pick N``, которым ``cast`` понимает выбор картины из этого списка.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.json_value import JsonValue

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def search_results(plans: list[Plan]) -> list[JsonValue]:
    """Пункты меню круга поиска как контрактные записи, пронумерованные с единицы."""
    return [
        {
            "pick": number,
            "key": plan.picture.key,
            "title": plan.picture.title,
            "year": plan.picture.year,
            "kind": plan.picture.kind,
        }
        for number, plan in enumerate(plans, start=1)
    ]
