"""Список картин по запросу как тело ``POST /api/search``: только форма, не поиск.

Поиск делает :func:`torrcast.usecases.discover.search_circle.search_circle`
(:func:`hass.searching.searching`); здесь - его выдача, пронумерованная под флаг
``--pick N``, которым ``cast`` понимает выбор картины из этого списка.

🔴 Договор с карточкой Home Assistant - поле ``default``. ``True`` стоит ровно у той
записи, чей номер включил бы голый ``POST /api/play`` без ``--pick``
(:func:`torrcast.usecases.choice.enter_take.enter_take`), и читает его
:func:`custom_components.torrcast.browse.search_media`: она ставит эту запись первой,
потому что штатный обработчик Home Assistant играет ``results[0]``. Порядок самих
записей продуктовый и остаётся продуктовым - взятый пункт называет поле, а не место.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.json_value import JsonValue

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def search_results(plans: list[Plan], taken: int) -> list[JsonValue]:
    """Пункты меню круга поиска как контрактные записи, пронумерованные с единицы.

    ``taken`` - номер картины, которую взял бы голый показ: у неё, и только у неё,
    ``default`` истинно.
    """
    return [
        {
            "pick": number,
            "key": plan.picture.key,
            "title": plan.picture.title,
            "year": plan.picture.year,
            "kind": plan.picture.kind,
            "default": number == taken,
        }
        for number, plan in enumerate(plans, start=1)
    ]
