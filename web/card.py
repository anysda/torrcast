"""Карточка одной картины: ``GET /api/card/{key}?query=...``.

Ключ адресует картину в круге, который **тем же поиском**, что и ``/api/search``,
находит запрос из строки доводов - карточка не хранит своего пула раздач, а спрашивает
его заново, как и обещает договор (ключ без запроса ничей). Описание и рейтинг едут
фоновым добором (:class:`torrcast.usecases.facts.Facts`) и не задерживают ответ: не
приехало - поле ``null`` и заголовок ``X-Torrcast-Partial``, страница переспросит сама.

Пустое поле недоездом НЕ считается: у картины без статьи описания не будет никогда, и
заголовок стоит только там, где переспрашивать есть смысл (:func:`_answer`).

Переспрос с ``wait=1`` - долгий: ответ держится, пока тело не изменится или не доедет
целиком, но не дольше :data:`WAIT`. Короткий опрос раз в две секунды бросал страницу
после пятого захода со скелетом вместо описания и слал по 4-6 GET на картину.
"""

from __future__ import annotations

import json
import time
from typing import Final

from hass.hit_posters import hits
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from torrcast.domain.spoken_title import spoken_title
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.state_store.slot import store
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.select.plan import Plan
from web.answer import Answer
from web.card_lookup import card_lookup
from web.card_poster import CardPoster
from web.card_seasons import card_seasons
from web.episode_lookup import GRACE, EpisodeLookup
from web.rating_score import rating_score
from web.refusal import refusal
from web.related_lookup import RelatedLookup
from web.request import Request
from web.warm_wiring import WARM

#: Префикс, под которым живёт вся карточка; ключ картины - хвост пути после него.
_PREFIX = "/api/card/"
#: Заголовок, которым карточка метит недоехавшее описание, рейтинг, родню или серии.
_PARTIAL = "X-Torrcast-Partial"
#: Потолок долгого переспроса: переживает первый контакт разбора серий с роем, который
#: завёл ещё первый GET. Равные 8 с кончали заход раньше разбора, и мёртвый рой сериала
#: стоил странице третьего запроса (стенд `.104`: Knightfall, серии ответили на 8.19 с).
WAIT: Final = GRACE + 1.0
#: Шаг, которым долгий переспрос оглядывается на фоновые доборы.
_TICK: Final = 0.25
#: Разбор серий той раздачи, которую играл бы показ - один кэш на весь процесс
#: (см. :class:`web.episode_lookup.EpisodeLookup`).
_episodes = EpisodeLookup(engines=TorrServer)
#: Родня картины по Wikidata (§8) - тот же приём фонового кэша, что и у серий.
_related = RelatedLookup(franchise=FACTS.franchise.of, passport=FACTS.passport.of, warm=WARM.ask)
#: Приговор обложки - тот же, что у выдачи поиска и полки (:mod:`web.card_poster`).
_poster = CardPoster(offer=hits.offer)
#: Сколько долгий заход досиживает после первой перемены, пока доезжает остальное: части
#: приходят порознь (стенд `.104`: родня и серии через 2.1 с, приговор обложки через 2.7 с),
#: и ответ на каждую перемену стоил странице лишнего запроса.
_SETTLE: Final = 1.0


def card(request: Request) -> Answer:
    """Собрать карточку по ключу картины, найденной тем же кругом, что и поиск."""
    query = request.query.get("query", "")
    if not query.strip():
        return refusal(400, "no_query")
    key = request.path[len(_PREFIX) :]
    config = load_config()
    try:
        # Согретый круг отдаётся сразу (:mod:`web.warm_cache`), несогретый считается
        # тут же и вперёд фона: живой запрос не встаёт в очередь прогрева.
        plans = WARM.take(query)
    except TorrcastError as failed:
        return refusal(409, str(failed))
    plan, pick = card_lookup(plans, key)
    if plan is None:
        return refusal(404, "not_found")
    return _answer(plan, config, pick, WAIT if request.query.get("wait") == "1" else 0.0)


def _answer(plan: Plan, config: Config, pick: int, wait: float = 0.0) -> Answer:
    """Тело ответа плюс заголовок недоехавшей части: справка, обложка, родня, серии."""
    picture = plan.picture
    entry = store().load().get(picture.key)
    facts = MenuFacts([(picture.title, picture.year, picture.kind)], budget=0.0)
    facts.start()
    until = time.monotonic() + wait
    first, partial = _body(plan, config, pick, entry, facts)
    body = first
    while partial and time.monotonic() < until:
        time.sleep(_TICK)
        body, partial = _body(plan, config, pick, entry, facts)
        if body != first:
            until = min(until, time.monotonic() + _SETTLE)
    extra = ((_PARTIAL, "1"),) if partial else ()
    return Answer(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), extra=extra)


def _body(
    plan: Plan, config: Config, pick: int, entry: Entry | None, facts: MenuFacts
) -> tuple[dict[str, JsonValue], bool]:
    """Тело как оно есть сейчас и «что-то ещё в пути»; пустая справка - готовый ответ."""
    picture = plan.picture
    fact = facts.ready(picture.title, picture.year)
    told = facts.answered(picture.title, picture.year)
    seasons, seasons_partial = card_seasons(plan, entry, config.torrserver_url, _episodes)
    series = picture.kind == "tv"
    related = _others(picture.key, _related.of(picture.title, series))
    # Родня без идущего похода - молчание источника, а не недоезд: ждать её этой карточке
    # нечего, и страница переспрашивала её до исчерпания заходов.
    coming = related is None and _related.waiting(picture.title, series)
    poster, judging = _poster.of(picture)
    body: dict[str, JsonValue] = {
        # Номер картины В КРУГЕ: им «Играть» просит показ ровно ту, которую человек
        # видит, а не ту, что круг взял бы по умолчанию (ТЗ §4.3).
        "pick": pick,
        "title": picture.title,
        "shown": spoken_title(picture.title, picture.original or ""),
        "original": picture.original or None,
        "year": picture.year,
        "kind": picture.kind,
        "runtime": plan.runtime,
        "runtime_estimated": plan.runtime_estimated,
        "rating": rating_score(fact.rating),
        "blurb": fact.about if told else None,
        "poster": poster,
        "voices": _voices(plan),
        "resumable": entry.resumable if entry else False,
        "label": entry.label if entry else "",
        "seasons": seasons,
        "related": related,
        "releases_count": len(picture.releases),
        "sources_count": _sources_count(picture.releases),
    }
    return body, not told or seasons_partial or coming or judging


def _others(key: str, related: list[JsonValue] | None) -> list[JsonValue] | None:
    """Полка родни - ДРУГИЕ части франшизы (ТЗ §8): сама картина себе не родня.

    Wikidata запрошенное отсеивает сама (:func:`torrcast.domain.facts.kin_query`), но
    голое имя серии паспорт намеренно отдаёт статьёй ФРАНШИЗЫ, и тогда первая картина
    приезжает в родню к себе же: замер 10-09-2026 на стенде `.104` - под карточкой
    `movie:джон-уик:2014` пятой плиткой стоял «Джон Уик» 2014 года, ведущий на неё же.
    """
    if related is None:
        return None
    return [tile for tile in related if not isinstance(tile, dict) or tile.get("key") != key]


def _voices(plan: Plan) -> list[JsonValue]:
    """Дорожки как их называют раздачи: студия, лучшее её качество и сумма сидов.

    ТЗ называет источником ``Release.dubbed`` - это булево, имени в нём нет. Дорожку
    видно только по :attr:`Release.studios`, и группировка идёт по ней.
    """
    lead = {studio.name for studio in plan.ranked[0].studios} if plan.ranked else set()
    groups: dict[str, list[Release]] = {}
    for release in plan.picture.releases:
        for studio in release.studios:
            groups.setdefault(studio.name, []).append(release)
    return [
        {
            "name": name,
            "quality": max(items, key=lambda r: r.height).quality or "",
            "seeders": sum(r.seeders for r in items),
            "default": name in lead,
        }
        for name, items in groups.items()
    ]


def _sources_count(releases: list[Release]) -> int:
    names = {release.indexer for release in releases if release.indexer}
    names.update(name for release in releases for name in release.indexers)
    return len(names)
