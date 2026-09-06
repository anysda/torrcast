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
from torrcast.cli.parse_args import parse_args
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from torrcast.ports.progress.slot import progress
from torrcast.ports.state_store.slot import store
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.select.plan import Plan
from web.answer import Answer
from web.refusal import refusal
from web.request import Request

#: Префикс, под которым живёт вся карточка; ключ картины - хвост пути после него.
_PREFIX = "/api/card/"
#: Заголовок, которым карточка метит недоехавшее описание, рейтинг или родню.
_PARTIAL = "X-Torrcast-Partial"


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
    return _answer(plan)


def _answer(plan: Plan) -> Answer:
    """Тело ответа плюс заголовок недоехавшей части, если справка ещё не готова."""
    picture = plan.picture
    entry = store().load().get(picture.key)
    facts = MenuFacts([(picture.title, picture.year, picture.kind)], budget=0.0)
    facts.start()
    fact = facts.ready(picture.title, picture.year)
    body: dict[str, JsonValue] = {
        "title": picture.title,
        "original": picture.original or None,
        "year": picture.year,
        "kind": picture.kind,
        "runtime": plan.runtime,
        "runtime_estimated": plan.runtime_estimated,
        "rating": fact.rating or None,
        "blurb": fact.about or None,
        "poster": poster_name(picture.title, picture.year, picture.kind),
        "voices": _voices(plan),
        "resumable": entry.resumable if entry else False,
        "label": entry.label if entry else "",
        "seasons": _seasons(picture, entry),
        "related": None,
        "releases_count": len(picture.releases),
        "sources_count": _sources_count(picture.releases),
    }
    extra = () if fact else ((_PARTIAL, "1"),)
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


def _seasons(picture: Picture, entry: Entry | None) -> list[JsonValue]:
    """Сезоны и серии: из закладки, если она есть, иначе только счётчик из раздач."""
    if picture.kind != "tv":
        return []
    if entry is not None and entry.episodes:
        return _seasons_from_entry(entry)
    numbers = sorted({season for release in picture.releases for season in _named_seasons(release)})
    return [{"n": n, "episodes": []} for n in numbers]


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


def _sources_count(releases: list[Release]) -> int:
    names = {release.indexer for release in releases if release.indexer}
    names.update(name for release in releases for name in release.indexers)
    return len(names)
