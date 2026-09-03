"""Шаг ``POST /api/search``: найти круг картин, запомнить его порядок и назвать дефолт.

Своих правил тут нет, и это главное свойство единицы. Профиль приёмника берётся тем же
паспортом, что и у показа (:func:`torrcast.usecases.cast_command._cmd_play._cmd_play`), и
накладывается на настройки той же :func:`torrcast.domain.tune.tune`: список судится про тот
приёмник, на который поедет показ (TC-241). Поиск идёт тем же
:func:`~torrcast.usecases.discover.search_circle.search_circle`, что и консоль.

🔴 Картину по умолчанию называет та же :func:`~torrcast.usecases.choice.enter_take.enter_take`,
чей номер включает голый ``POST /api/play`` без ``--pick``. Спрашивать её тут своим правилом
запрещено: «первая живая» и «между фильмом и сериалом - сериал» это решения владельца
(TC-812 и 02-09-2026), их правят, и списанная эвристика разъехалась бы с продуктом молча.
Договор с карточкой - булево поле ``default`` у записи выдачи
(:func:`hass.search_results.search_results`): ровно один пункт списка назван взятым, и
:func:`custom_components.torrcast.browse.search_media` ставит его первым - штатный
обработчик Home Assistant играет ``results[0]``.

🔴 Показанный порядок запоминается тем же механизмом, что и меню консоли
(:meth:`torrcast.adapters.filesystem.release_pins.ReleasePins.remember_menu`), и тем же
ключом (``args.title_query``), каким его читает
:func:`torrcast.usecases.choice._pick_plan._pick_plan`. Без записи номер из выдачи моста -
не адрес: состав выдачи гуляет от захода к заходу, а память от старой таблицы
``cast releases`` того же запроса давала залипающий отказ - человеку, ткнувшему в карточку,
продукт советовал сходить в терминал.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from hass.hit_posters import hits
from hass.refused_error import RefusedError
from hass.search_results import search_results
from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.filesystem.release_pins import pins
from torrcast.cli.parse_args import parse_args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
from torrcast.domain.profile import Profile
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.slot import progress
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.discover.search_circle import search_circle

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan

#: Чем ищется выдача: тот же круг поиска, что у показа, либо ответ подделки в тесте.
Search = Callable[[Config, "Args", Progress, Profile], list["Plan"]]
#: Кто такой приёмник на том конце: паспорт устройства или ключ из настроек.
Detect = Callable[[Config], Choice]
#: Куда ложится показанный порядок картин: ключ и имя под их номерами.
Remember = Callable[[str, list[tuple[str, str]]], None]
#: Кто называет картинку той находки, что прошла приговор: список этим держится до него.
Offer = Callable[[list[JsonValue]], list[JsonValue]]

#: Боевые исполнители шага - ровно те же, что у консоли. Кладёт их мост
#: (:class:`hass.bridge.Bridge`), подделки называют щупы и зеркала.
SEARCH: Search = search_circle
DETECT: Detect = detector.detect
REMEMBER: Remember = pins.remember_menu
OFFER: Offer = hits.offer


def searching(
    config: Config,
    query: str,
    search: Search,
    detect: Detect,
    remember: Remember,
    offer: Offer | None = None,
) -> list[JsonValue]:
    """Круг картин запроса как тело ответа: номера под ``--pick N`` и взятый пункт.

    Порядок записей - порядок продукта, и переставлять его тут нечем: номер ``pick`` в
    записи и есть адрес картины в запомненном порядке. Взятый пункт назван полем, а не
    местом в списке.

    ``offer`` дописывает имя картинки только тем записям, чья картина прошла приговор
    (:class:`hass.hit_posters.HitPosters`: год сверен И адрес постера назван источником) -
    не каждой находке, иначе список нёс бы рамку вокруг пустоты. Приговор ждётся тут же, в
    сети, до возврата списка: пачка стоит на нём полдесятка запросов разом, а не по три на
    находку, и это осознанный размен - плитка не бывает битой ценой этого ожидания. Не
    названный зовущим, он берётся из :data:`OFFER` в момент вызова, а не в момент
    объявления: подделка в зеркале ставится именно туда.
    """
    named = OFFER if offer is None else offer
    chosen = detect(config)
    args = parse_args([query])
    try:
        plans = search(tune(config, chosen.profile), args, progress(), chosen.profile)
    except TorrcastError as refusal:
        raise RefusedError(str(refusal)) from refusal
    remember(args.title_query, [(plan.picture.key, _named(plan.picture)) for plan in plans])
    return named(search_results(plans, enter_take(plans, args.title_query).number))
