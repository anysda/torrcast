"""Карточка одной картины: ``GET /api/card/{key}?query=...``.

Ключ адресует картину в круге, который **тем же поиском**, что и ``/api/search``,
находит запрос из строки доводов - карточка не хранит своего пула раздач, а спрашивает
его заново, как и обещает договор (ключ без запроса ничей). Описание и рейтинг едут
фоновым добором (:class:`torrcast.usecases.facts.Facts`) и не задерживают ответ: не
приехало - поле ``null`` и заголовок ``X-Torrcast-Partial``, страница переспросит сама.
"""

from __future__ import annotations

import json

from hass.poster_name import poster_name
from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from torrcast.ports.progress.slot import progress
from torrcast.ports.state_store.slot import store
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.select.plan import Plan
from web.answer import Answer
from web.episode_lookup import EpisodeLookup
from web.rating_score import rating_score
from web.refusal import refusal
from web.related_lookup import RelatedLookup
from web.request import Request

#: Префикс, под которым живёт вся карточка; ключ картины - хвост пути после него.
_PREFIX = "/api/card/"
#: Заголовок, которым карточка метит недоехавшее описание, рейтинг, родню или серии.
_PARTIAL = "X-Torrcast-Partial"
#: Разбор серий той раздачи, которую играл бы показ - один кэш на весь процесс
#: (см. :class:`web.episode_lookup.EpisodeLookup`).
_episodes = EpisodeLookup(engines=TorrServer)
#: Родня картины по Wikidata (§8) - тот же приём фонового кэша, что и у серий.
_related = RelatedLookup(franchise=FACTS.franchise.of)


def card(request: Request) -> Answer:
    """Собрать карточку по ключу картины, найденной тем же кругом, что и поиск."""
    query = request.query.get("query", "")
    if not query.strip():
        return refusal(400, "no_query")
    key = request.path[len(_PREFIX) :]
    config = load_config()
    chosen = detector.detect(config)
    args = parse_args([query])
    try:
        plans = search_circle(tune(config, chosen.profile), args, progress(), chosen.profile)
    except TorrcastError as failed:
        return refusal(409, str(failed))
    plan = next((p for p in plans if p.picture.key == key), None)
    if plan is None:
        return refusal(404, "not_found")
    return _answer(plan, config)


def _answer(plan: Plan, config: Config) -> Answer:
    """Тело ответа плюс заголовок недоехавшей части: справка или список серий."""
    picture = plan.picture
    entry = store().load().get(picture.key)
    facts = MenuFacts([(picture.title, picture.year, picture.kind)], budget=0.0)
    facts.start()
    fact = facts.ready(picture.title, picture.year)
    seasons, seasons_partial = _seasons(plan, entry, config.torrserver_url)
    related = _related.of(picture.title, picture.kind == "tv")
    body: dict[str, JsonValue] = {
        "title": picture.title,
        "original": picture.original or None,
        "year": picture.year,
        "kind": picture.kind,
        "runtime": plan.runtime,
        "runtime_estimated": plan.runtime_estimated,
        "rating": rating_score(fact.rating),
        "blurb": fact.about or None,
        "poster": poster_name(picture.title, picture.year, picture.kind),
        "voices": _voices(plan),
        "resumable": entry.resumable if entry else False,
        "label": entry.label if entry else "",
        "seasons": seasons,
        "related": related,
        "releases_count": len(picture.releases),
        "sources_count": _sources_count(picture.releases),
    }
    partial = not fact or seasons_partial or related is None
    extra = ((_PARTIAL, "1"),) if partial else ()
    return Answer(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), extra=extra)


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


def _seasons(plan: Plan, entry: Entry | None, base_url: str) -> tuple[list[JsonValue], bool]:
    """Сезоны и серии: из закладки, если она есть; иначе разбор выбранной раздачи.

    Разбор фоновый (:class:`web.episode_lookup.EpisodeLookup`): не готов - вернулась
    ``None``, и карточка честно показывает только счётчик сезонов из имён раздач, помечая
    тело недоехавшим (второй элемент пары), совсем как справка (:data:`_PARTIAL`).
    """
    picture = plan.picture
    if picture.kind != "tv":
        return [], False
    if entry is not None and entry.episodes:
        return _seasons_from_entry(entry), False
    numbers = sorted({season for release in picture.releases for season in _named_seasons(release)})
    fallback: list[JsonValue] = [{"n": n, "episodes": []} for n in numbers]
    if not plan.ranked:
        return fallback, False
    table = _episodes.table(plan.ranked[0], base_url)
    if table is None:
        return fallback, True
    return (_seasons_from_table(table), False) if table else (fallback, False)


def _named_seasons(release: Release) -> tuple[int, ...]:
    if release.seasons:
        return release.seasons
    return (release.season,) if release.season else ()


def _seasons_from_entry(entry: Entry) -> list[JsonValue]:
    at = entry.where(entry.season or 0, entry.episode or 0)
    seasons: dict[int, list[JsonValue]] = {}
    for index, row in enumerate(entry.episodes):
        season, episode = row[0], row[1]
        current = index == at
        seasons.setdefault(season, []).append(
            {
                "n": episode,
                "dur": entry.dur if current else 0.0,
                "watched": entry.watched if current else index < at,
                "pos": entry.pos if current else 0.0,
            }
        )
    return [{"n": n, "episodes": eps} for n, eps in sorted(seasons.items())]


def _seasons_from_table(table: list[list[int]]) -> list[JsonValue]:
    """Серии из разбора раздачи: картину никто не смотрел, отмечать нечего."""
    seasons: dict[int, list[JsonValue]] = {}
    for row in table:
        season, episode = row[0], row[1]
        blank: dict[str, JsonValue] = {"n": episode, "dur": 0.0, "watched": False, "pos": 0.0}
        seasons.setdefault(season, []).append(blank)
    return [{"n": n, "episodes": eps} for n, eps in sorted(seasons.items())]


def _sources_count(releases: list[Release]) -> int:
    names = {release.indexer for release in releases if release.indexer}
    names.update(name for release in releases for name in release.indexers)
    return len(names)
