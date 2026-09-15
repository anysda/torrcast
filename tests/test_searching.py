"""Зеркало шага поиска моста: взятый пункт, память показанного порядка и профиль.

Круг поиска тут настоящий (:func:`torrcast.usecases.discover.search_circle.search_circle`),
подделан только заход в сеть (:mod:`tests.usecases.discover.world`) и паспорт приёмника:
настоящий звонит в сеть, а мерить надо не звонок, а профиль. Память показанного порядка
НЕ подделана: под ``--pick`` её читает настоящий выбор, и подмена сделала бы зеркало
зеркалом самого себя.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import hass.searching as searching_module
from hass.hit_posters import hits
from hass.searching import searching
from tests.test_warm_cache import _TOLD
from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.adapters.filesystem.release_pins import pins
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.json_value import JsonValue
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS, Profile
from torrcast.domain.tune import tune
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.select.plan import Plan
from web.circle_disk import CircleDisk
from web.warm_cache import WarmCache

_CONFIG = Config(prowlarr_apikey="KEY", tv="10.0.1.7")
#: Выдача, на которой верх списка и взятая картина РАСХОДЯТСЯ: у первой части рой мёртв
#: (:data:`torrcast.domain.rank_settings.ALIVE_SEEDERS` - 5), и голый показ берёт вторую.
_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=2),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p | D", "b", size_gb=5.0, seeders=180),
    row("Тачки 3 / Cars 3 (2017) BDRip 1080p | D", "c", size_gb=6.0, seeders=90),
]


def _search(config: Config, args: Args, progress: Any, profile: Profile) -> list[Plan]:
    """Тот же круг поиска, что у консоли, с подделанным клиентом индексеров."""
    wire_catalogue()
    client = Indexer(answers={"тачки": _CARS})
    return search_circle(
        config,
        args,
        progress,
        profile,
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: Origin(),
    )


def _plans() -> list[Plan]:
    """Та же выдача, снятая мимо шага: с ней и сверяется его ответ."""
    return _search(_CONFIG, Args(query=["тачки"]), Said(), CAUTIOUS)


def _cautious(_config: Config) -> Choice:
    return Choice(CAUTIOUS, "тест")


def _offer(results: list[JsonValue]) -> list[JsonValue]:
    """Двойник называния картинок: имя вместо похода в справку.

    Настоящий (:data:`hass.searching.OFFER`) ушёл бы за постерами в сеть прямо из
    зеркала, а мерить тут надо не Википедию, а то, что имя доезжает до записи выдачи.
    """
    return [
        {**result, "poster": "картинка"} if isinstance(result, dict) else result
        for result in results
    ]


def _records(results: list[JsonValue]) -> list[dict[str, Any]]:
    """Записи выдачи под своим видом: договор обещает объекты, а не любой JSON."""
    assert all(isinstance(result, dict) for result in results), "запись выдачи - объект"
    return cast("list[dict[str, Any]]", results)


def test_the_flagged_record_is_the_picture_a_bare_play_would_take() -> None:
    """Один запрос - один фильм: помечен тот пункт, который включит голый ``/api/play``.

    Штатный обработчик Home Assistant играет ``results[0]``, а голый показ - приговор
    :func:`~torrcast.usecases.choice.enter_take.enter_take`. Пока помеченным был верх
    списка, «тачки» голосом давали «Тачки», а голым показом «Тачки 2»: у первой части
    рой мёртв.
    """
    plans = _plans()

    results = searching(_CONFIG, "тачки", _search, _cautious, pins.remember_menu, _offer)

    records = _records(results)
    flagged = [record["pick"] for record in records if record["default"]]
    assert flagged == [enter_take(plans, "тачки").number], "помечен не тот, кого возьмёт показ"
    assert flagged != [1], "на этой выдаче взятая картина НЕ верх списка - иначе мерить нечего"
    assert records[flagged[0] - 1]["title"] == "Тачки 2"


def test_the_search_step_remembers_the_order_it_showed() -> None:
    """Номер из выдачи - адрес: под ним стоит та картина, которую шаг назвал.

    Память кладётся тем же механизмом и тем же ключом, каким её читает выбор, поэтому
    ``--pick N`` берёт картину под номером N. Без записи оставалась чужая - от старой
    консольной таблицы того же запроса, - и человеку, ткнувшему в карточку, продукт
    отвечал отказом и советом сходить в терминал за свежими номерами.
    """
    plans = _plans()
    stale = [(plans[2].picture.key, "Тачки 3"), (plans[0].picture.key, "Тачки")]
    pins.remember_menu("тачки", stale)

    searching(_CONFIG, "тачки", _search, _cautious, pins.remember_menu, _offer)

    assert pins.recalled_picture("тачки", 2)[0] == plans[1].picture.key
    assert _pick_plan(plans, None, pick=2, asked="тачки").picture.title == "Тачки 2"


def test_the_search_step_judges_by_the_receivers_own_profile() -> None:
    """Список судится про тот приёмник, на который поедет показ (TC-241), а не вслепую."""
    seen: list[tuple[Config, Profile]] = []

    def watching(config: Config, args: Args, progress: Any, profile: Profile) -> list[Plan]:
        seen.append((config, profile))
        return _search(config, args, progress, profile)

    searching(
        _CONFIG,
        "тачки",
        watching,
        lambda _c: Choice(ANDROID_TV, "тест"),
        pins.remember_menu,
        _offer,
    )

    assert seen[0][1] is ANDROID_TV, "профиль приёмника до круга поиска не доехал"
    assert seen[0][0] == tune(_CONFIG, ANDROID_TV), "пороги профиля не наложены"


def test_every_record_carries_the_name_of_its_picture() -> None:
    """Каждой находке достаётся имя её картинки: без него список остаётся текстом.

    Имя дописывается уже готовой выдаче и ничего в ней не сдвигает: номер ``pick`` и
    метка взятого пункта остаются на своих местах, а картинка догоняет список отдельным
    запросом за ней.
    """
    records = _records(searching(_CONFIG, "тачки", _search, _cautious, pins.remember_menu, _offer))

    assert [record.get("poster") for record in records] == ["картинка"] * len(records)
    assert [record["pick"] for record in records] == [1, 2, 3]


def test_a_card_after_the_search_step_takes_its_circle_without_a_second_trip() -> None:
    """🔴 ``/api/search`` и следом ``/api/card`` той же картины прошли индексеры дважды: +3.6 с."""
    asked: list[str] = []

    def counted(config: Config, args: Args, progress: Any, profile: Profile) -> list[Plan]:
        asked.append(args.title_query)
        return _search(config, args, progress, profile)

    def _second(_query: str) -> list[Plan]:
        raise AssertionError("карточка пошла по индексерам второй раз")

    warm = WarmCache(circle=_second, blurbs=lambda _p: None, spawn=lambda _job: None)
    searching(_CONFIG, "тачки", counted, _cautious, pins.remember_menu, _offer, warm=warm)

    assert [plan.picture.title for plan in warm.take("тачки")][:1] == ["Тачки"]
    assert asked == ["тачки"]


def test_the_search_step_after_a_restart_counts_a_fresh_circle_instead_of_the_disk_one(
    tmp_path: Path,
) -> None:
    """Выдача HA шла свежим кругом; общий кэш отдавал ей круг с диска возрастом до суток."""
    asked: list[str] = []

    def counted(config: Config, args: Args, progress: Any, profile: Profile) -> list[Plan]:
        asked.append(args.title_query)
        return _search(config, args, progress, profile)

    disk = CircleDisk(path=lambda: tmp_path / "circles.json")
    disk.keep("тачки", _TOLD)
    old = _plans()[2:]
    warm = WarmCache(
        lambda _q: [], lambda _p: None, lambda _job: None, disk=disk, replay=lambda *_: old
    )
    records = searching(_CONFIG, "тачки", counted, _cautious, pins.remember_menu, _offer, warm=warm)

    assert (asked, len(records)) == (["тачки"], len(_plans()))


def test_the_visible_list_asks_its_posters_ahead_of_the_shelves() -> None:
    """Приговор выдачи идёт срочным: полки главной и «похожие» не занимают его минуту."""
    assert hits.urgent == searching_module.OFFER
