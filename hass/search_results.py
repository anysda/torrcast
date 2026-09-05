"""Список картин по запросу как тело ``POST /api/search``: только форма, не поиск.

Поиск делает :func:`torrcast.usecases.discover.search_circle.search_circle`
(:func:`hass.searching.searching`); здесь - его выдача, пронумерованная под флаг
``--pick N``, которым ``cast`` понимает выбор картины из этого списка.

🔴 Договор с карточкой Home Assistant - поле ``default``. ``True`` стоит ровно у той
записи, чей номер включил бы голый ``POST /api/play`` без ``--pick``
(:func:`torrcast.usecases.choice.enter_take.enter_take`), и читает его
:func:`custom_components.torrcast.search_media.search_media`: она ставит эту запись первой,
потому что штатный обработчик Home Assistant играет ``results[0]``. Порядок самих
записей продуктовый и остаётся продуктовым - взятый пункт называет поле, а не место.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.json_value import JsonValue
from torrcast.domain.spoken_title import spoken_title
from torrcast.usecases.choice._named import _named

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def search_results(plans: list[Plan], taken: int) -> list[JsonValue]:
    """Пункты меню круга поиска как контрактные записи, пронумерованные с единицы.

    ``taken`` - номер картины, которую взял бы голый показ: у неё, и только у неё,
    ``default`` истинно.

    Оригинальное имя едет отдельным полем, потому что у части находок русской статьи нет
    вовсе, а английская лежит ровно под ним: без этого поля картинка такой находки была
    бы недостижима (:func:`hass.hit_ask._about`).

    🔴 ``shown`` - имя картины ДЛЯ ЧЕЛОВЕКА, и решает его продукт
    (:func:`torrcast.domain.spoken_title.spoken_title`), тем же правилом, каким зовёт
    картину меню ``cast`` и запись показа (:attr:`torrcast.domain.playback_snapshot.
    PlaybackSnapshot.spoken`). Без него карточка звала находку сырым ``title``, и под
    ``language=en`` один запрос на одном стенде давал человеку две выдачи: меню -
    ``Back to the Future (1985)``, карточка - «Назад в будущее (1985)».

    Полем, а не подменой ``title``: сырое имя из ``title`` карточке не показывают, но по
    нему ищут картинку (:func:`hass.hit_ask._about` спрашивает русский раздел Википедии и
    кладёт постер на общую с карточкой плеера полку). Локализованное имя в ``title``
    увело бы этот поиск на английское имя, а полку разбило бы на две записи про одну
    картину. Английское ``original`` подписью тоже не станет - у отечественной картины
    его нет вовсе.

    🔴 ``named`` - вся СТРОКА пункта, какой её собирает меню ``cast``
    (:func:`torrcast.usecases.choice._named._named`, тот же вызов, что у
    :func:`torrcast.usecases.choice.head_line.head_line`): имя, год и пометки вида.
    Готовой строкой, а не пометкой отдельным полем, потому что второе место, где строку
    СОБИРАЮТ, - это второе правило: карточка уже собирала ``"{имя} ({год})"`` своей рукой
    и о сериале молчала вовсе, а человек в списке видел одинаковые строки у сериала и у
    фильма-тёзки. Сложить пометку на стороне ``custom_components`` нельзя и по-другому:
    пометка локализована (``, сериал`` / ``, series``), а язык знает только продукт.

    Пометка «имя только по-русски» тут есть (``item=True``): из этого списка человек
    ВЫБИРАЕТ, ровно как из меню консоли, и обязан видеть, что английского имени у пункта
    нет. Год неизвестен - в строке стоит ``(?)``, как и в консоли: у списка находок это
    не украшение, а различитель тёзок. Больше в строке ничего и нет: строка карточки и
    строка меню сходятся буква в букву, и стеречь их сходство есть чем
    (``tests/hass_integration/test_search_media.py``).
    """
    return [
        {
            "pick": number,
            "key": plan.picture.key,
            "title": plan.picture.title,
            "shown": spoken_title(plan.picture.title, plan.picture.original or ""),
            "named": _named(plan.picture, item=True),
            "year": plan.picture.year,
            "kind": plan.picture.kind,
            "original": plan.picture.original or "",
            "default": number == taken,
        }
        for number, plan in enumerate(plans, start=1)
    ]
